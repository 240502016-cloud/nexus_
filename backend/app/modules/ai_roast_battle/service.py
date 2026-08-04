from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.modules.ai_commentator.models import CommentatorEvent
from app.modules.ai_roast_battle.models import RoastCandidate, RoastProfile, RoastRound, RoastSessionPlayer, RoastVote
from app.modules.ai_roast_battle.schemas import RoastProfileUpdate, RoastSessionCreate
from app.modules.highlight_generator.models import HighlightMarker, HighlightRecording
from app.modules.party_lore.service import find_entries
from app.platform.events import append_event
from app.platform.jobs import enqueue_job
from app.platform.models import BackgroundJob, ExperienceSession, ExperienceSessionPlayer, utcnow
from app.platform.sessions import create_session, ensure_session_access, ensure_session_player


def _profile_snapshot(profile: RoastProfile | None) -> dict:
    if profile is None:
        return {"roast_enabled": False, "maximum_intensity": 1, "allowed_topics": [], "allow_party_lore": False, "allow_highlights": True, "allow_recent_failures": False, "blocked_terms": [], "consent_version": 1}
    return {"roast_enabled": profile.roast_enabled, "maximum_intensity": profile.maximum_intensity, "allowed_topics": profile.allowed_topics, "allow_party_lore": profile.allow_party_lore, "allow_highlights": profile.allow_highlights, "allow_recent_failures": profile.allow_recent_failures, "blocked_terms": profile.blocked_terms, "consent_version": profile.consent_version}


def update_profile(db: Session, *, server_id: int, actor: User, payload: RoastProfileUpdate) -> RoastProfile:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    profile = db.get(RoastProfile, {"server_id": server_id, "user_id": actor.id})
    values = payload.model_dump()
    if profile is None:
        profile = RoastProfile(server_id=server_id, user_id=actor.id, **values)
        db.add(profile)
    else:
        if any(getattr(profile, key) != value for key, value in values.items()):
            profile.consent_version += 1
        for key, value in values.items():
            setattr(profile, key, value)
    db.commit()
    return db.get(RoastProfile, {"server_id": server_id, "user_id": actor.id})


def _roast_session(db: Session, session_id: str, *, lock: bool = False) -> ExperienceSession:
    query = db.query(ExperienceSession).filter(ExperienceSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = query.first()
    if not session or session.module_type != "ai_roast_battle":
        raise HTTPException(status_code=404, detail="Roast Battle oturumu bulunamadı")
    return session


def create_roast_session(db: Session, *, server_id: int, actor: User, payload: RoastSessionCreate, idempotency_key: str) -> ExperienceSession:
    session = create_session(db, server_id=server_id, module_type="ai_roast_battle", owner=actor, idempotency_key=idempotency_key, settings={"mode": "BALANCED_SPOTLIGHT", "requested_intensity": payload.requested_intensity, "target_order": payload.player_ids, "current_round": 0})
    if db.query(RoastSessionPlayer).filter(RoastSessionPlayer.session_id == session.id).count() == 3:
        return session
    if actor.id not in payload.player_ids:
        raise HTTPException(status_code=422, detail="Oturum sahibi oyuncular arasında olmalı")
    server = db.get(Server, server_id)
    users = {row.id: row for row in db.query(User).filter(User.id.in_(payload.player_ids)).all()}
    if set(users) != set(payload.player_ids):
        raise HTTPException(status_code=422, detail="Oyunculardan biri bulunamadı")
    for user in users.values():
        ensure_server_member(db, server, user)
    existing_players = {row.user_id: row for row in session.players}
    for seat, user_id in enumerate(payload.player_ids):
        if user_id not in existing_players:
            db.add(ExperienceSessionPlayer(session_id=session.id, user_id=user_id, seat=seat, ready=False))
        else:
            existing_players[user_id].seat = seat
            existing_players[user_id].ready = False
        profile = db.get(RoastProfile, {"server_id": server_id, "user_id": user_id})
        snapshot = _profile_snapshot(profile)
        db.add(RoastSessionPlayer(session_id=session.id, user_id=user_id, seat=seat, consent_version=snapshot["consent_version"], profile_snapshot=snapshot))
    session.status = "consent_pending"
    session.revision += 1
    append_event(db, session, "roast.consent_requested", {"player_ids": payload.player_ids}, idempotency_key=f"roast:consent:{session.id}")
    db.commit()
    return _roast_session(db, session.id)


def session_to_dict(db: Session, session: ExperienceSession) -> dict:
    rows = db.query(RoastSessionPlayer).filter(RoastSessionPlayer.session_id == session.id).order_by(RoastSessionPlayer.seat).all()
    return {"id": session.id, "server_id": session.server_id, "player_ids": [row.user_id for row in rows], "consent": {row.user_id: row.consent_state.upper() for row in rows}, "requested_intensity": int((session.settings or {}).get("requested_intensity", 1)), "status": session.status.upper(), "current_round": int((session.settings or {}).get("current_round", 0)), "revision": session.revision}


def submit_consent(db: Session, *, session_id: str, actor: User, decision: str, consent_version: int) -> ExperienceSession:
    session = _roast_session(db, session_id, lock=True)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    row = db.get(RoastSessionPlayer, {"session_id": session.id, "user_id": actor.id})
    profile = db.get(RoastProfile, {"server_id": session.server_id, "user_id": actor.id})
    if decision == "READY":
        if not profile or not profile.roast_enabled or profile.consent_version != consent_version:
            raise HTTPException(status_code=409, detail="Güncel ve açık roast profiliyle onay gerekli")
        row.consent_state = "ready"
        row.consent_version = profile.consent_version
        row.profile_snapshot = _profile_snapshot(profile)
        row.consented_at = utcnow()
        db.get(ExperienceSessionPlayer, {"session_id": session.id, "user_id": actor.id}).ready = True
    elif decision == "DECLINE":
        row.consent_state = "declined"
        session.status = "cancelled"
        session.ended_at = utcnow()
    else:
        row.consent_state = "revoked"
        row.revoked_at = utcnow()
        session.status = "cancelled"
        session.ended_at = utcnow()
        db.query(BackgroundJob).filter(BackgroundJob.session_id == session.id, BackgroundJob.status.in_(["queued", "running"])).update({BackgroundJob.cancel_requested: True}, synchronize_session=False)
    if session.status == "consent_pending" and db.query(RoastSessionPlayer).filter(RoastSessionPlayer.session_id == session.id, RoastSessionPlayer.consent_state != "ready").count() == 0:
        session.status = "active"
        session.started_at = utcnow()
    session.revision += 1
    append_event(db, session, "roast.consent_changed", {"user_id": actor.id, "decision": decision, "status": session.status.upper()}, idempotency_key=f"roast:consent:{actor.id}:{session.revision}")
    db.commit()
    return _roast_session(db, session.id)


def _source_for_target(db: Session, session: ExperienceSession, target_id: int, snapshot: dict, actor: User) -> dict | None:
    recent_events = db.query(CommentatorEvent).filter(CommentatorEvent.session_id == session.id).order_by(CommentatorEvent.created_at.desc()).limit(50).all()
    for event in recent_events:
        if target_id in event.actor_player_ids and event.category not in {"ARGUMENT"} and event.source_confidence >= 0.85:
            return {"type": "GAMING_EVENT", "id": event.id, "fact": event.normalized_summary, "topic": event.category, "confidence": event.source_confidence}
    if snapshot.get("allow_highlights", True):
        markers = db.query(HighlightMarker).join(HighlightRecording, HighlightRecording.id == HighlightMarker.recording_id).filter(HighlightRecording.server_id == session.server_id).order_by(HighlightMarker.created_at.desc()).limit(50).all()
        for marker in markers:
            if target_id in marker.participant_player_ids and marker.summary:
                return {"type": "HIGHLIGHT", "id": marker.id, "fact": marker.summary[:280], "topic": marker.category_hint, "confidence": 1.0}
    if snapshot.get("allow_party_lore"):
        lore = find_entries(db, server_id=session.server_id, actor=actor, module="ai_roast_battle", participant_ids=[target_id], limit=1)
        if lore:
            return {"type": "PARTY_LORE", "id": lore[0].id, "fact": lore[0].summary[:280], "topic": lore[0].category, "confidence": 1.0}
    return None


def start_next_round(db: Session, *, session_id: str, actor: User) -> RoastRound:
    session = _roast_session(db, session_id, lock=True)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    if session.status != "active":
        raise HTTPException(status_code=409, detail="Oturum aktif değil")
    pending = db.query(RoastRound).filter(RoastRound.session_id == session.id, RoastRound.status.in_(["generating", "voting"])).first()
    if pending:
        return pending
    settings = dict(session.settings or {})
    round_number = int(settings.get("current_round", 0)) + 1
    order = settings["target_order"]
    if round_number > len(order):
        raise HTTPException(status_code=409, detail="Tüm roast turları tamamlandı")
    target_id = int(order[round_number - 1])
    target_row = db.get(RoastSessionPlayer, {"session_id": session.id, "user_id": target_id})
    source = _source_for_target(db, session, target_id, target_row.profile_snapshot, actor)
    round_row = RoastRound(session_id=session.id, round_number=round_number, target_player_id=target_id, effective_intensity=min(int(settings["requested_intensity"]), int(target_row.profile_snapshot["maximum_intensity"]), 2), source_snapshot=source or {}, status="generating" if source else "skipped")
    db.add(round_row)
    db.flush()
    settings["current_round"] = round_number
    session.settings = settings
    session.revision += 1
    if source:
        enqueue_job(db, module="ai_roast_battle", job_type="roast.generate_review", idempotency_key=f"roast:{round_row.id}", input_ref={"round_id": round_row.id}, session_id=session.id, actor_id=actor.id, priority=6)
    else:
        round_row.completed_at = utcnow()
    append_event(db, session, "roast.round_started" if source else "roast.round_skipped", {"round_id": round_row.id, "round_number": round_number, "target_player_id": target_id}, idempotency_key=f"roast:round:{round_number}")
    db.commit()
    return db.get(RoastRound, round_row.id)


def round_to_dict(db: Session, row: RoastRound) -> dict:
    candidate = db.get(RoastCandidate, row.selected_candidate_id) if row.selected_candidate_id else None
    return {"id": row.id, "session_id": row.session_id, "round_number": row.round_number, "target_player_id": row.target_player_id, "effective_intensity": row.effective_intensity, "status": row.status.upper(), "candidate_id": candidate.id if candidate else None, "roast_text": candidate.roast_text if candidate else None, "angle": candidate.angle if candidate else None}


def vote(db: Session, *, candidate_id: str, actor: User, vote_type: str) -> RoastVote:
    candidate = db.get(RoastCandidate, candidate_id)
    round_row = db.get(RoastRound, candidate.round_id) if candidate else None
    session = _roast_session(db, round_row.session_id, lock=True) if round_row else None
    if not candidate or not round_row or not session:
        raise HTTPException(status_code=404, detail="Roast adayı bulunamadı")
    ensure_session_player(db, session, actor.id)
    if round_row.status != "voting":
        raise HTTPException(status_code=409, detail="Tur oylamada değil")
    contribution = {"FUNNY": 2.0, "OKAY": 0.5, "PASS": 0.0}[vote_type]
    row = db.query(RoastVote).filter_by(candidate_id=candidate.id, voter_id=actor.id).first()
    if row is None:
        row = RoastVote(candidate_id=candidate.id, voter_id=actor.id)
        db.add(row)
    row.vote_type = vote_type
    row.is_target_vote = actor.id == candidate.target_player_id
    row.score_contribution = contribution
    db.flush()
    if db.query(RoastVote).filter(RoastVote.candidate_id == candidate.id).count() == 3:
        round_row.status = "completed"
        round_row.completed_at = utcnow()
        target = db.get(RoastSessionPlayer, {"session_id": session.id, "user_id": candidate.target_player_id})
        target.total_score += sum(v.score_contribution for v in db.query(RoastVote).filter_by(candidate_id=candidate.id).all())
        if round_row.round_number >= 3:
            session.status = "ended"
            session.ended_at = utcnow()
        session.revision += 1
        append_event(db, session, "roast.round_completed", {"round_id": round_row.id, "candidate_id": candidate.id}, idempotency_key=f"roast:complete:{round_row.id}")
    db.commit()
    return row
