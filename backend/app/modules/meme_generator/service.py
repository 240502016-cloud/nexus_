from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authz import ensure_server_member
from app.core.models import Server, ServerMember, User
from app.modules.meme_generator import schemas
from app.modules.meme_generator.models import (
    GeneratedMeme,
    MemeCaptionCandidate,
    MemeFeedback,
    MemeGeneration,
    MemePlayerPreference,
)
from app.modules.meme_generator.renderer import render_card
from app.modules.meme_generator.safety import contains_hard_blocked_text
from app.modules.meme_generator.templates import (
    BUILTIN_TEMPLATES,
    TEMPLATES_BY_KEY,
    public_template,
)
from app.modules.meme_generator.trigger_engine import eligible_templates, score_event
from app.modules.party_lore.models import LoreEntry
from app.modules.party_lore.service import record_lore_usage
from app.platform.events import add_outbox_event, append_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceSession, ExperienceSessionPlayer, MediaAsset, new_uuid, utcnow
from app.platform.sessions import ensure_session_access, ensure_session_player


def _server_for_member(db: Session, server_id: int, actor: User) -> Server:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    return server


def _server_user_ids(db: Session, server: Server) -> set[int]:
    return {server.owner_id} | {
        row[0]
        for row in db.query(ServerMember.user_id).filter(ServerMember.server_id == server.id).all()
    }


def _generation_for_member(db: Session, generation_id: str, actor: User) -> MemeGeneration:
    generation = db.get(MemeGeneration, generation_id)
    if not generation:
        raise HTTPException(status_code=404, detail="Meme üretim işi bulunamadı")
    _server_for_member(db, generation.server_id, actor)
    return generation


def _preference(db: Session, server_id: int, user_id: int) -> MemePlayerPreference | None:
    return db.get(MemePlayerPreference, {"server_id": server_id, "user_id": user_id})


def create_generation(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: schemas.MemeGenerationCreate,
    idempotency_key: str,
) -> MemeGeneration:
    server = _server_for_member(db, server_id, actor)
    event = payload.event
    if event.server_id != server_id:
        raise HTTPException(status_code=422, detail="Event server_id adresle eşleşmiyor")
    if event.occurred_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="occurred_at timezone içermeli")
    if event.occurred_at > utcnow() + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="Event zamanı gelecekte olamaz")

    existing = (
        db.query(MemeGeneration)
        .filter(
            MemeGeneration.server_id == server_id,
            (
                (MemeGeneration.external_event_id == event.event_id)
                | (
                    (MemeGeneration.requested_by_id == actor.id)
                    & (MemeGeneration.idempotency_key == idempotency_key)
                )
            ),
        )
        .order_by(MemeGeneration.created_at.desc())
        .first()
    )
    if existing:
        return existing

    mentioned_ids = set(event.actor_player_ids) | set(event.target_player_ids)
    if not mentioned_ids.issubset(_server_user_ids(db, server)):
        raise HTTPException(status_code=422, detail="Event yalnızca sunucu oyuncularını içerebilir")
    if actor.id not in mentioned_ids and event.source == "MANUAL":
        # A server member can describe the party, but remains the accountable requester.
        mentioned_ids.add(actor.id)

    session = None
    if event.session_id:
        session = db.get(ExperienceSession, event.session_id)
        if not session or session.server_id != server_id:
            raise HTTPException(status_code=422, detail="Oturum bu sunucuya ait değil")
        ensure_session_access(db, session, actor)
        ensure_session_player(db, session, actor.id)
        player_ids = {
            row[0]
            for row in db.query(ExperienceSessionPlayer.user_id)
            .filter(ExperienceSessionPlayer.session_id == session.id)
            .all()
        }
        if not (set(event.actor_player_ids) | set(event.target_player_ids)).issubset(player_ids):
            raise HTTPException(status_code=422, detail="Event oyuncuları oturumda yer almıyor")

    relevant_ids = set(event.actor_player_ids) | set(event.target_player_ids)
    preferences = {user_id: _preference(db, server_id, user_id) for user_id in relevant_ids}
    if any(pref is not None and not pref.memes_enabled for pref in preferences.values()):
        raise HTTPException(status_code=409, detail="Bir oyuncu meme kullanımını kapatmış")
    for target_id in event.target_player_ids:
        pref = preferences.get(target_id)
        if pref is not None and not pref.allow_as_target:
            raise HTTPException(status_code=409, detail="Hedef oyuncu meme hedefi olmayı kapatmış")

    harshness_caps = [pref.maximum_harshness for pref in preferences.values() if pref is not None]
    effective_harshness = min([payload.desired_harshness, 2, *harshness_caps])
    worthiness, reasoning_code, category = score_event(event)
    templates = eligible_templates(
        category=category,
        preferred_formats=list(payload.preferred_formats),
    )
    worthy = reasoning_code == "WORTHY"
    generation = MemeGeneration(
        server_id=server_id,
        session_id=event.session_id,
        requested_by_id=actor.id,
        idempotency_key=idempotency_key,
        external_event_id=event.event_id,
        source=event.source,
        event_snapshot=event.model_dump(mode="json"),
        preferred_formats=list(payload.preferred_formats),
        desired_harshness=effective_harshness,
        status="queued" if worthy else "filtered",
        meme_worthiness_score=worthiness,
        reasoning_code=reasoning_code,
        category=category,
        eligible_template_keys=[template.key for template in templates],
    )
    db.add(generation)
    db.flush()
    if worthy:
        job = enqueue_job(
            db,
            module="meme_generator",
            job_type="meme.caption",
            idempotency_key=f"caption:{server_id}:{event.event_id}",
            input_ref={"generation_id": generation.id},
            session_id=event.session_id,
            actor_id=actor.id,
            priority=5,
        )
        generation.background_job_id = job.id
    add_outbox_event(
        db,
        topic="meme_generator.events",
        aggregate_type="meme_generation",
        aggregate_id=generation.id,
        event_type="meme.generation_queued" if worthy else "meme.generation_filtered",
        payload={
            "generation_id": generation.id,
            "server_id": server_id,
            "event_id": event.event_id,
            "reasoning_code": reasoning_code,
            "score": worthiness,
        },
    )
    db.commit()
    return db.get(MemeGeneration, generation.id)


def generation_to_accepted(generation: MemeGeneration) -> dict:
    return {
        "job_id": generation.id,
        "event_id": generation.external_event_id,
        "status": generation.status.upper(),
        "meme_worthy": generation.reasoning_code == "WORTHY",
        "meme_worthiness_score": generation.meme_worthiness_score,
        "reasoning_code": generation.reasoning_code,
    }


def candidate_to_dict(candidate: MemeCaptionCandidate) -> dict:
    template = TEMPLATES_BY_KEY[candidate.template_key]
    return {
        "id": candidate.id,
        "rank": candidate.rank,
        "template_key": candidate.template_key,
        "template_version": candidate.template_version,
        "template_name": template.name,
        "category": candidate.category,
        "captions": candidate.captions,
        "target_player_id": candidate.target_player_id,
        "lore_references": candidate.lore_references,
        "harshness": candidate.harshness,
        "quality_score": candidate.quality_score,
    }


def get_candidates(db: Session, *, generation_id: str, actor: User) -> dict:
    generation = _generation_for_member(db, generation_id, actor)
    return {
        "job_id": generation.id,
        "status": generation.status.upper(),
        "meme_worthy": generation.reasoning_code == "WORTHY",
        "meme_worthiness_score": generation.meme_worthiness_score,
        "reasoning_code": generation.reasoning_code,
        "error_code": generation.error_code,
        "candidates": [candidate_to_dict(item) for item in generation.candidates],
    }


def _validated_captions(template_key: str, base: dict, overrides: dict) -> dict[str, str]:
    template = TEMPLATES_BY_KEY.get(template_key)
    if not template:
        raise HTTPException(status_code=422, detail="Bilinmeyen meme şablonu")
    zone_keys = {zone.key for zone in template.zones}
    if set(overrides) - zone_keys:
        raise HTTPException(status_code=422, detail="Şablonda bulunmayan caption alanı")
    captions = {**base, **overrides}
    if set(captions) != zone_keys:
        raise HTTPException(status_code=422, detail="Tüm caption alanları gerekli")
    for zone in template.zones:
        text = " ".join(str(captions[zone.key]).split())
        if not text or len(text) > zone.max_chars:
            raise HTTPException(status_code=422, detail=f"{zone.key} caption sınırı geçersiz")
        captions[zone.key] = text
    if sum(len(value.split()) for value in captions.values()) > 18:
        raise HTTPException(status_code=422, detail="Caption toplam 18 kelimeyi geçemez")
    return captions


def render_generation(
    db: Session,
    *,
    generation_id: str,
    actor: User,
    payload: schemas.RenderMemeRequest,
) -> GeneratedMeme:
    generation = _generation_for_member(db, generation_id, actor)
    candidate = db.get(MemeCaptionCandidate, payload.candidate_id)
    if not candidate or candidate.generation_id != generation.id:
        raise HTTPException(status_code=404, detail="Caption adayı bulunamadı")
    template_key = payload.template_key or candidate.template_key
    if template_key not in generation.eligible_template_keys:
        raise HTTPException(status_code=422, detail="Şablon bu event için uygun değil")
    captions = _validated_captions(template_key, candidate.captions, payload.caption_overrides)

    relevant_ids = {candidate.target_player_id, generation.requested_by_id} - {None}
    blocked_topics: set[str] = set()
    for user_id in relevant_ids:
        pref = _preference(db, generation.server_id, int(user_id))
        if pref:
            blocked_topics.update(pref.blocked_topics)
    joined = " ".join(captions.values()).casefold()
    if contains_hard_blocked_text(joined):
        raise HTTPException(status_code=422, detail="Caption güvenlik politikasını ihlal ediyor")
    if any(topic and topic in joined for topic in blocked_topics):
        raise HTTPException(status_code=422, detail="Caption oyuncu konu sınırını ihlal ediyor")

    meme_id = new_uuid()
    storage_key = f"{generation.server_id}/{meme_id}.png"
    target_path = Path(settings.generated_media_dir) / storage_key
    rendered = render_card(TEMPLATES_BY_KEY[template_key], captions, target_path)
    digest = hashlib.sha256(rendered).hexdigest()
    asset = MediaAsset(
        server_id=generation.server_id,
        owner_id=actor.id,
        session_id=generation.session_id,
        kind="generated_meme",
        storage_key=storage_key,
        mime_type="image/png",
        size_bytes=len(rendered),
        sha256=digest,
    )
    db.add(asset)
    db.flush()
    meme = GeneratedMeme(
        id=meme_id,
        generation_id=generation.id,
        candidate_id=candidate.id,
        asset_id=asset.id,
        server_id=generation.server_id,
        session_id=generation.session_id,
        created_by_id=actor.id,
        template_key=template_key,
        template_version=TEMPLATES_BY_KEY[template_key].version,
        category=candidate.category,
        captions_snapshot=captions,
        target_player_id=candidate.target_player_id,
        lore_references=candidate.lore_references,
    )
    db.add(meme)
    if generation.session_id:
        session = db.get(ExperienceSession, generation.session_id)
        if session:
            session.revision += 1
            append_event(
                db,
                session,
                "meme.rendered",
                {"meme_id": meme.id, "generation_id": generation.id},
                idempotency_key=f"meme:rendered:{meme.id}",
            )
    for lore_id in candidate.lore_references:
        entry = db.get(LoreEntry, lore_id)
        if entry:
            record_lore_usage(
                db,
                entry=entry,
                actor=actor,
                module="meme_generator",
                request_id=f"meme:{meme.id}",
                context={"generation_id": generation.id},
            )
    add_outbox_event(
        db,
        topic="meme_generator.events",
        aggregate_type="generated_meme",
        aggregate_id=meme.id,
        event_type="meme.rendered",
        payload={"meme_id": meme.id, "asset_id": asset.id, "server_id": generation.server_id},
    )
    try:
        db.commit()
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    return db.get(GeneratedMeme, meme.id)


def generated_meme_to_dict(db: Session, meme: GeneratedMeme) -> dict:
    asset = db.get(MediaAsset, meme.asset_id)
    return {
        "id": meme.id,
        "job_id": meme.generation_id,
        "template_key": meme.template_key,
        "template_name": TEMPLATES_BY_KEY[meme.template_key].name,
        "category": meme.category,
        "captions": meme.captions_snapshot,
        "target_player_id": meme.target_player_id,
        "asset_url": f"/memes/assets/{asset.id}",
        "width": meme.width,
        "height": meme.height,
        "mime_type": asset.mime_type,
        "byte_size": asset.size_bytes,
        "created_at": meme.created_at,
    }


def submit_feedback(
    db: Session,
    *,
    meme_id: str,
    actor: User,
    payload: schemas.MemeFeedbackCreate,
) -> MemeFeedback:
    meme = db.get(GeneratedMeme, meme_id)
    if not meme or meme.deleted_at:
        raise HTTPException(status_code=404, detail="Meme bulunamadı")
    _server_for_member(db, meme.server_id, actor)
    feedback = (
        db.query(MemeFeedback)
        .filter(MemeFeedback.meme_id == meme.id, MemeFeedback.user_id == actor.id)
        .first()
    )
    if feedback is None:
        feedback = MemeFeedback(meme_id=meme.id, user_id=actor.id)
        db.add(feedback)
    feedback.feedback_type = payload.feedback_type
    feedback.details = payload.details
    db.commit()
    return feedback


def update_preference(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: schemas.MemePreferenceUpdate,
) -> MemePlayerPreference:
    _server_for_member(db, server_id, actor)
    preference = _preference(db, server_id, actor.id)
    values = payload.model_dump()
    if preference is None:
        preference = MemePlayerPreference(server_id=server_id, user_id=actor.id, **values)
        db.add(preference)
    else:
        for key, value in values.items():
            setattr(preference, key, value)
    db.commit()
    return _preference(db, server_id, actor.id)


def resolve_asset(db: Session, *, asset_id: str, actor: User) -> tuple[MediaAsset, Path]:
    asset = db.get(MediaAsset, asset_id)
    if not asset or asset.kind != "generated_meme" or asset.status != "active":
        raise HTTPException(status_code=404, detail="Meme dosyası bulunamadı")
    _server_for_member(db, asset.server_id, actor)
    root = Path(settings.generated_media_dir).resolve()
    path = (root / asset.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Meme dosyası bulunamadı")
    return asset, path


def delete_meme(db: Session, *, meme_id: str, actor: User) -> None:
    meme = db.get(GeneratedMeme, meme_id)
    if not meme or meme.deleted_at:
        return
    _server_for_member(db, meme.server_id, actor)
    if meme.created_by_id != actor.id:
        raise HTTPException(status_code=403, detail="Meme'yi yalnız oluşturan kullanıcı silebilir")
    asset = db.get(MediaAsset, meme.asset_id)
    meme.deleted_at = utcnow()
    asset.status = "deleted"
    asset.deleted_at = utcnow()
    root = Path(settings.generated_media_dir).resolve()
    path = (root / asset.storage_key).resolve()
    if root in path.parents:
        path.unlink(missing_ok=True)
    db.commit()


def list_templates() -> list[dict]:
    return [public_template(template) for template in BUILTIN_TEMPLATES]
