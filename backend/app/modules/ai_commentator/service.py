from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.modules.ai_commentator.models import (
    CommentaryCooldown,
    CommentaryFeedback,
    CommentatorEvent,
    CommentatorPlayerPreference,
    CommentatorSessionPlayer,
    GeneratedCommentary,
)
from app.modules.ai_commentator.profiles import BUILTIN_PROFILES, get_profile
from app.modules.ai_commentator.schemas import (
    CommentarySessionCreate,
    CommentarySessionUpdate,
    CommentatorEventCreate,
    CommentatorPreferenceUpdate,
)
from app.modules.ai_commentator.trigger_engine import decide_trigger
from app.platform.events import add_outbox_event, append_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceSession, ExperienceSessionPlayer, utcnow
from app.platform.sessions import (
    _check_revision,
    _get_session,
    create_active_session,
    ensure_session_access,
    ensure_session_player,
)


_ALLOWED_ATTRIBUTE_KEYS = {
    "secondsAfterRoundStart",
    "teammatesAlive",
    "streak",
    "score",
    "count",
    "objective",
    "item",
    "location",
}


def _commentator_session(db: Session, session_id: str, *, lock: bool = False) -> ExperienceSession:
    session = _get_session(db, session_id, lock=lock)
    if session.module_type != "ai_commentator":
        raise HTTPException(status_code=404, detail="AI Commentator oturumu bulunamadı")
    return session


def _settings(session: ExperienceSession) -> dict:
    return {
        "game_key": "manual",
        "profile_key": "dry_sarcastic",
        "intensity": "NORMAL",
        "silent_mode": False,
        "tts_enabled": False,
        "current_tone": "UNKNOWN",
        **(session.settings or {}),
    }


def _preference_to_dict(preference: CommentatorPlayerPreference | None) -> dict:
    if preference is None:
        return {
            "commentary_enabled": True,
            "allow_targeted_jokes": True,
            "allow_lore_references": True,
            "maximum_harshness": 1,
            "preferred_humor_styles": ["GENTLE"],
            "blocked_topics": [],
            "tts_enabled": True,
        }
    return {
        "commentary_enabled": preference.commentary_enabled,
        "allow_targeted_jokes": preference.allow_targeted_jokes,
        "allow_lore_references": preference.allow_lore_references,
        "maximum_harshness": preference.maximum_harshness,
        "preferred_humor_styles": preference.preferred_humor_styles,
        "blocked_topics": preference.blocked_topics,
        "tts_enabled": preference.tts_enabled,
    }


def session_to_dict(session: ExperienceSession) -> dict:
    settings = _settings(session)
    return {
        "id": session.id,
        "server_id": session.server_id,
        "game_key": settings["game_key"],
        "player_ids": [player.user_id for player in session.players],
        "profile_key": settings["profile_key"],
        "intensity": settings["intensity"],
        "silent_mode": settings["silent_mode"],
        "text_to_speech_enabled": settings["tts_enabled"],
        "current_tone": settings["current_tone"],
        "status": session.status,
        "revision": session.revision,
        "output_channel_id": session.channel_id,
        "started_at": session.started_at or session.created_at,
        "ended_at": session.ended_at,
    }


def event_to_dict(event: CommentatorEvent) -> dict:
    return {
        "id": event.id,
        "event_id": event.external_event_id,
        "category": event.category,
        "summary": event.normalized_summary,
        "occurred_at": event.occurred_at,
        "trigger_score": event.trigger_score,
        "trigger_decision": event.trigger_decision,
        "processing_state": event.processing_state,
    }


def commentary_to_dict(commentary: GeneratedCommentary) -> dict:
    return {
        "id": commentary.id,
        "session_id": commentary.session_id,
        "source_event_ids": commentary.source_event_ids,
        "should_comment": commentary.should_comment,
        "commentary": commentary.commentary_text,
        "target_player_id": commentary.target_player_id,
        "tone": commentary.tone,
        "lore_references": commentary.lore_references,
        "confidence": commentary.confidence,
        "reason_code": commentary.reason_code,
        "dispatch_state": commentary.dispatch_state,
        "created_at": commentary.created_at,
        "delivered_at": commentary.delivered_at,
    }


def create_commentary_session(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: CommentarySessionCreate,
    idempotency_key: str,
) -> ExperienceSession:
    profile = get_profile(payload.profile_key)
    if not profile:
        raise HTTPException(status_code=422, detail="Bilinmeyen yorumcu profili")
    session = create_active_session(
        db,
        server_id=server_id,
        module_type="ai_commentator",
        owner=actor,
        player_ids=payload.player_ids,
        idempotency_key=idempotency_key,
        channel_id=payload.output_channel_id,
        settings={
            "game_key": payload.game_key,
            "profile_key": payload.profile_key,
            "intensity": payload.intensity,
            "silent_mode": False,
            "tts_enabled": payload.text_to_speech_enabled,
            "current_tone": "UNKNOWN",
        },
    )
    existing_ids = {
        row[0]
        for row in db.query(CommentatorSessionPlayer.user_id)
        .filter(CommentatorSessionPlayer.session_id == session.id)
        .all()
    }
    for player in session.players:
        if player.user_id in existing_ids:
            continue
        preference = db.get(
            CommentatorPlayerPreference,
            {"server_id": server_id, "user_id": player.user_id},
        )
        db.add(
            CommentatorSessionPlayer(
                session_id=session.id,
                user_id=player.user_id,
                preference_snapshot=_preference_to_dict(preference),
            )
        )
    db.commit()
    return _commentator_session(db, session.id)


def find_active_commentary_session(
    db: Session,
    *,
    server_id: int,
    actor: User,
) -> ExperienceSession | None:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    return (
        db.query(ExperienceSession)
        .join(
            ExperienceSessionPlayer,
            ExperienceSessionPlayer.session_id == ExperienceSession.id,
        )
        .filter(
            ExperienceSession.server_id == server_id,
            ExperienceSession.module_type == "ai_commentator",
            ExperienceSession.status == "active",
            ExperienceSessionPlayer.user_id == actor.id,
        )
        .order_by(ExperienceSession.created_at.desc())
        .first()
    )


def update_commentary_session(
    db: Session,
    *,
    session_id: str,
    actor: User,
    payload: CommentarySessionUpdate,
) -> ExperienceSession:
    session = _commentator_session(db, session_id, lock=True)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    _check_revision(session, payload.expected_revision)
    changes = payload.model_dump(exclude={"expected_revision"}, exclude_none=True)
    if not changes:
        return session
    if payload.profile_key is not None and not get_profile(payload.profile_key):
        raise HTTPException(status_code=422, detail="Bilinmeyen yorumcu profili")
    only_enabling_silence = changes == {"silent_mode": True}
    if session.owner_id != actor.id and not only_enabling_silence:
        raise HTTPException(
            status_code=403,
            detail="Diğer ayarları ve sessiz modu kapatmayı yalnızca oturum sahibi yapabilir",
        )
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Sona ermiş oturum değiştirilemez")

    mapped_changes = dict(changes)
    if "text_to_speech_enabled" in mapped_changes:
        mapped_changes["tts_enabled"] = mapped_changes.pop("text_to_speech_enabled")
    settings = _settings(session)
    settings.update(mapped_changes)
    session.settings = settings
    session.revision += 1
    append_event(
        db,
        session,
        "commentator.settings_changed",
        {"changed": sorted(mapped_changes), "actor_id": actor.id},
        idempotency_key=f"commentator:settings:{session.revision}",
    )
    db.commit()
    return _commentator_session(db, session.id)


def update_preference(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: CommentatorPreferenceUpdate,
) -> CommentatorPlayerPreference:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    preference = db.get(
        CommentatorPlayerPreference,
        {"server_id": server_id, "user_id": actor.id},
    )
    values = payload.model_dump()
    if preference is None:
        preference = CommentatorPlayerPreference(server_id=server_id, user_id=actor.id, **values)
        db.add(preference)
    else:
        for name, value in values.items():
            setattr(preference, name, value)
    active_session_rows = (
        db.query(CommentatorSessionPlayer)
        .join(ExperienceSession, ExperienceSession.id == CommentatorSessionPlayer.session_id)
        .filter(
            ExperienceSession.server_id == server_id,
            ExperienceSession.module_type == "ai_commentator",
            ExperienceSession.status == "active",
            CommentatorSessionPlayer.user_id == actor.id,
        )
        .all()
    )
    for row in active_session_rows:
        row.preference_snapshot = dict(values)
    db.commit()
    return db.get(
        CommentatorPlayerPreference,
        {"server_id": server_id, "user_id": actor.id},
    )


def _normalized_attributes(attributes: dict) -> dict:
    result: dict = {}
    for key in sorted(set(attributes).intersection(_ALLOWED_ATTRIBUTE_KEYS)):
        value = attributes[key]
        if isinstance(value, bool) or isinstance(value, (int, float)):
            result[key] = value
        elif isinstance(value, str):
            result[key] = value[:80]
    return result


def _deduplication_key(payload: CommentatorEventCreate, attributes: dict) -> str:
    stable = {
        "category": payload.category,
        "actors": sorted(payload.actor_player_ids),
        "targets": sorted(payload.target_player_ids),
        "match": payload.game.match_id,
        "round": payload.game.round_id,
        "attributes": attributes,
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def ingest_event(
    db: Session,
    *,
    session_id: str,
    actor: User,
    payload: CommentatorEventCreate,
) -> tuple[CommentatorEvent, str]:
    session = _commentator_session(db, session_id, lock=True)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Oturum event kabul etmiyor")
    settings = _settings(session)
    if payload.game.game_key != settings["game_key"]:
        raise HTTPException(status_code=422, detail="Event game_key oturumla eşleşmiyor")
    if payload.occurred_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="occurred_at timezone içermeli")
    if payload.occurred_at > utcnow() + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Event zamanı gelecekte olamaz")

    existing = (
        db.query(CommentatorEvent)
        .filter(
            CommentatorEvent.session_id == session.id,
            CommentatorEvent.external_event_id == payload.event_id,
        )
        .first()
    )
    if existing:
        state = "PENDING" if existing.trigger_decision == "GENERATE" else "FILTERED"
        return existing, state

    session_player_ids = {player.user_id for player in session.players}
    mentioned_ids = set(payload.actor_player_ids) | set(payload.target_player_ids)
    if not mentioned_ids.issubset(session_player_ids):
        raise HTTPException(status_code=422, detail="Event yalnızca oturum oyuncularını içerebilir")

    attributes = _normalized_attributes(payload.attributes)
    dedup_key = _deduplication_key(payload, attributes)
    dedup_window = timedelta(seconds=10 if payload.category in {"PLAYER_DEATH", "PLAYER_FAIL"} else 5)
    duplicate = False
    recent_same = (
        db.query(CommentatorEvent)
        .filter(
            CommentatorEvent.session_id == session.id,
            CommentatorEvent.deduplication_key == dedup_key,
        )
        .order_by(CommentatorEvent.occurred_at.desc())
        .first()
    )
    if recent_same:
        duplicate = abs(_aware(payload.occurred_at) - _aware(recent_same.occurred_at)) <= dedup_window

    preference_rows = {
        row.user_id: row
        for row in db.query(CommentatorSessionPlayer)
        .filter(CommentatorSessionPlayer.session_id == session.id)
        .all()
    }
    policy_ids = mentioned_ids or session_player_ids
    commentary_enabled = all(
        preference_rows[user_id].preference_snapshot.get("commentary_enabled", True)
        for user_id in policy_ids
    )
    if payload.target_player_ids:
        commentary_enabled = commentary_enabled and all(
            preference_rows[user_id].preference_snapshot.get("allow_targeted_jokes", True)
            for user_id in payload.target_player_ids
        )
    blocked_topics = {
        topic
        for user_id in policy_ids
        for topic in preference_rows[user_id].preference_snapshot.get("blocked_topics", [])
    }
    if any(topic and topic in payload.summary.casefold() for topic in blocked_topics):
        commentary_enabled = False

    now = utcnow()
    active_cooldowns = (
        db.query(CommentaryCooldown)
        .filter(
            CommentaryCooldown.session_id == session.id,
            CommentaryCooldown.cooldown_until > now,
        )
        .all()
    )
    global_cooldown = any(
        item.scope_type == "GLOBAL" and item.scope_key == "all" for item in active_cooldowns
    )
    category_cooldown = payload.category != "CLUTCH" and any(
        item.scope_type == "CATEGORY" and item.scope_key == payload.category
        for item in active_cooldowns
    )
    target_cooldown = any(
        item.scope_type == "PLAYER" and item.scope_key in {str(user_id) for user_id in mentioned_ids}
        for item in active_cooldowns
    )
    total_targets = sum(row.targeted_count for row in preference_rows.values())
    target_saturation = 0.0
    if payload.target_player_ids and total_targets >= 3:
        highest_share = max(
            preference_rows[user_id].targeted_count / total_targets
            for user_id in payload.target_player_ids
        )
        target_saturation = max(0.0, min(1.0, (highest_share - 0.4) / 0.6))
    stale = _aware(payload.occurred_at) < now - timedelta(minutes=10)
    result = decide_trigger(
        category=payload.category,
        importance=payload.importance,
        source_confidence=payload.confidence,
        source=payload.source,
        intensity=settings["intensity"],
        session_tone=payload.emotional_tone or settings["current_tone"],
        silent_mode=settings["silent_mode"],
        commentary_enabled=commentary_enabled,
        duplicate=duplicate,
        cooldown_active=global_cooldown or category_cooldown or target_cooldown,
        target_saturation=target_saturation,
    )
    decision = "STALE" if stale else result.decision
    state = "pending" if decision == "GENERATE" else "dropped"
    event = CommentatorEvent(
        session_id=session.id,
        external_event_id=payload.event_id,
        schema_version=payload.schema_version,
        source=payload.source,
        category=payload.category,
        occurred_at=payload.occurred_at,
        actor_player_ids=sorted(payload.actor_player_ids),
        target_player_ids=sorted(payload.target_player_ids),
        normalized_summary=payload.summary,
        game_context=payload.game.model_dump(exclude_none=True),
        normalized_attributes=attributes,
        importance=payload.importance,
        source_confidence=payload.confidence,
        novelty_score=0.5,
        trigger_score=result.score,
        trigger_decision=decision,
        deduplication_key=dedup_key,
        processing_state=state,
        processed_at=now if state == "dropped" else None,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(CommentatorEvent)
            .filter(
                CommentatorEvent.session_id == session.id,
                CommentatorEvent.external_event_id == payload.event_id,
            )
            .first()
        )
        if concurrent:
            replay_state = "PENDING" if concurrent.trigger_decision == "GENERATE" else "FILTERED"
            return concurrent, replay_state
        raise

    if decision == "GENERATE":
        enqueue_job(
            db,
            module="ai_commentator",
            job_type="commentary.generate",
            session_id=session.id,
            actor_id=actor.id,
            idempotency_key=f"commentary:event:{event.id}",
            input_ref={"event_id": event.id},
            priority=10,
        )
    session.revision += 1
    append_event(
        db,
        session,
        "commentator.event_ingested",
        {
            "event_id": event.id,
            "external_event_id": event.external_event_id,
            "category": event.category,
            "trigger_decision": decision,
        },
        idempotency_key=f"commentator:event:{event.id}",
    )
    db.commit()
    response_state = "DEDUPLICATED" if duplicate else ("PENDING" if state == "pending" else "FILTERED")
    return db.get(CommentatorEvent, event.id), response_state


def get_history(db: Session, *, session_id: str, actor: User, limit: int = 100) -> dict:
    session = _commentator_session(db, session_id)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    events = (
        db.query(CommentatorEvent)
        .filter(CommentatorEvent.session_id == session.id)
        .order_by(CommentatorEvent.occurred_at.desc())
        .limit(limit)
        .all()
    )
    commentary = (
        db.query(GeneratedCommentary)
        .filter(GeneratedCommentary.session_id == session.id)
        .order_by(GeneratedCommentary.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "session": session_to_dict(session),
        "events": [event_to_dict(event) for event in reversed(events)],
        "commentary": [commentary_to_dict(item) for item in reversed(commentary)],
    }


def submit_feedback(
    db: Session,
    *,
    commentary_id: str,
    actor: User,
    feedback_type: str,
    details: str | None,
) -> CommentaryFeedback:
    commentary = db.get(GeneratedCommentary, commentary_id)
    if not commentary:
        raise HTTPException(status_code=404, detail="Yorum bulunamadı")
    session = _commentator_session(db, commentary.session_id)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    feedback = (
        db.query(CommentaryFeedback)
        .filter(
            CommentaryFeedback.commentary_id == commentary.id,
            CommentaryFeedback.user_id == actor.id,
        )
        .first()
    )
    if feedback is None:
        feedback = CommentaryFeedback(
            commentary_id=commentary.id,
            user_id=actor.id,
            feedback_type=feedback_type,
            details=details,
        )
        db.add(feedback)
    else:
        feedback.feedback_type = feedback_type
        feedback.details = details
    add_outbox_event(
        db,
        topic="ai_commentator.events",
        aggregate_type="generated_commentary",
        aggregate_id=commentary.id,
        event_type="commentary.feedback_recorded",
        payload={
            "commentary_id": commentary.id,
            "session_id": session.id,
            "user_id": actor.id,
            "feedback_type": feedback_type,
        },
    )
    db.commit()
    db.refresh(feedback)
    return feedback


def end_commentary_session(
    db: Session,
    *,
    session_id: str,
    actor: User,
    expected_revision: int,
) -> ExperienceSession:
    session = _commentator_session(db, session_id, lock=True)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    if session.status == "ended":
        return session
    _check_revision(session, expected_revision)
    if session.owner_id != actor.id:
        raise HTTPException(status_code=403, detail="Oturumu yalnızca sahibi bitirebilir")
    session.status = "ended"
    session.ended_at = utcnow()
    session.revision += 1
    append_event(
        db,
        session,
        "session.ended",
        {"actor_id": actor.id},
        idempotency_key="session:end",
    )
    db.commit()
    return _commentator_session(db, session.id)


def list_profiles() -> list[dict]:
    return [{key: value for key, value in profile.items() if key != "style"} for profile in BUILTIN_PROFILES.values()]
