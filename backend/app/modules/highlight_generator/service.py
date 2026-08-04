from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authz import ensure_server_member
from app.core.models import Server, ServerMember, User
from app.modules.highlight_generator.models import (
    HighlightCandidate,
    HighlightFeedback,
    HighlightMarker,
    HighlightRecording,
    RenderedHighlight,
)
from app.modules.highlight_generator.schemas import (
    HighlightFeedbackCreate,
    MarkerCreate,
    RecordingCreate,
    RenderHighlightCreate,
)
from app.platform.events import add_outbox_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceSession, MediaAsset, utcnow
from app.platform.sessions import ensure_session_access, ensure_session_player


MIME_EXTENSION = {"video/mp4": ".mp4", "video/x-matroska": ".mkv"}
PADDING = {
    "SKILL": (8_000, 5_000),
    "COMEDY": (12_000, 8_000),
    "FAILURE": (10_000, 7_000),
    "CHAOS": (12_000, 8_000),
    "LORE_WORTHY": (12_000, 8_000),
}


def _server_for_member(db: Session, server_id: int, actor: User) -> Server:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    return server


def _recording_for_member(db: Session, recording_id: str, actor: User) -> HighlightRecording:
    recording = db.get(HighlightRecording, recording_id)
    if not recording or recording.deleted_at:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    _server_for_member(db, recording.server_id, actor)
    return recording


def _server_user_ids(db: Session, server: Server) -> set[int]:
    return {server.owner_id} | {
        row[0]
        for row in db.query(ServerMember.user_id).filter(ServerMember.server_id == server.id).all()
    }


def create_recording(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: RecordingCreate,
    idempotency_key: str,
) -> HighlightRecording:
    _server_for_member(db, server_id, actor)
    existing = (
        db.query(HighlightRecording)
        .filter(
            HighlightRecording.server_id == server_id,
            HighlightRecording.uploaded_by_id == actor.id,
            HighlightRecording.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return existing
    if payload.session_id:
        session = db.get(ExperienceSession, payload.session_id)
        if not session or session.server_id != server_id:
            raise HTTPException(status_code=422, detail="Oturum bu sunucuya ait değil")
        ensure_session_access(db, session, actor)
        ensure_session_player(db, session, actor.id)
    recording = HighlightRecording(
        server_id=server_id,
        session_id=payload.session_id,
        uploaded_by_id=actor.id,
        idempotency_key=idempotency_key,
        source_type=payload.source_type,
        original_filename=payload.original_filename,
        declared_mime_type=payload.content_type,
        declared_byte_size=payload.byte_size,
    )
    db.add(recording)
    db.flush()
    add_outbox_event(
        db,
        topic="highlight_generator.events",
        aggregate_type="highlight_recording",
        aggregate_id=recording.id,
        event_type="highlight.recording_created",
        payload={"recording_id": recording.id, "server_id": server_id},
    )
    db.commit()
    return db.get(HighlightRecording, recording.id)


async def receive_recording_content(
    db: Session,
    *,
    recording_id: str,
    actor: User,
    stream,
    content_length: int | None,
) -> HighlightRecording:
    recording = _recording_for_member(db, recording_id, actor)
    if recording.uploaded_by_id != actor.id:
        raise HTTPException(status_code=403, detail="Kaydı yalnız oluşturan kullanıcı yükleyebilir")
    if recording.status != "awaiting_upload":
        return recording
    if content_length is not None and content_length != recording.declared_byte_size:
        raise HTTPException(status_code=422, detail="Content-Length bildirilen boyutla eşleşmiyor")

    root = Path(settings.highlight_media_dir).resolve()
    storage_key = f"originals/{recording.server_id}/{recording.id}{MIME_EXTENSION[recording.declared_mime_type]}"
    final_path = (root / storage_key).resolve()
    if root not in final_path.parents:
        raise HTTPException(status_code=422, detail="Geçersiz storage key")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = final_path.with_suffix(final_path.suffix + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with part_path.open("wb") as output:
            async for chunk in stream:
                if not chunk:
                    continue
                received += len(chunk)
                if received > recording.declared_byte_size or received > settings.highlight_max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Video boyut sınırını aşıyor")
                digest.update(chunk)
                output.write(chunk)
        if received != recording.declared_byte_size:
            raise HTTPException(status_code=422, detail="Yüklenen byte sayısı bildirilen boyutla eşleşmiyor")
        part_path.replace(final_path)
    except Exception:
        part_path.unlink(missing_ok=True)
        raise

    asset = MediaAsset(
        server_id=recording.server_id,
        owner_id=actor.id,
        session_id=recording.session_id,
        kind="highlight_recording",
        storage_key=storage_key,
        mime_type=recording.declared_mime_type,
        size_bytes=received,
        sha256=digest.hexdigest(),
    )
    db.add(asset)
    db.flush()
    recording.asset_id = asset.id
    recording.storage_key = storage_key
    recording.byte_size = received
    recording.sha256 = digest.hexdigest()
    recording.status = "uploaded"
    recording.uploaded_at = utcnow()
    job = enqueue_job(
        db,
        module="highlight_generator",
        job_type="highlight.probe",
        idempotency_key=f"probe:{recording.id}:{recording.sha256}",
        input_ref={"recording_id": recording.id},
        session_id=recording.session_id,
        actor_id=actor.id,
        priority=10,
    )
    recording.probe_job_id = job.id
    try:
        db.commit()
    except Exception:
        final_path.unlink(missing_ok=True)
        raise
    return db.get(HighlightRecording, recording.id)


def recording_to_dict(recording: HighlightRecording) -> dict:
    return {
        "id": recording.id,
        "server_id": recording.server_id,
        "session_id": recording.session_id,
        "source_type": recording.source_type,
        "original_filename": recording.original_filename,
        "status": recording.status.upper(),
        "upload_url": f"/highlight/recordings/{recording.id}/content" if recording.status == "awaiting_upload" else None,
        "byte_size": recording.byte_size,
        "duration_ms": recording.duration_ms,
        "width": recording.width,
        "height": recording.height,
        "has_audio": recording.has_audio,
        "error_code": recording.error_code,
        "created_at": recording.created_at,
    }


def create_marker(
    db: Session,
    *,
    recording_id: str,
    actor: User,
    payload: MarkerCreate,
) -> HighlightCandidate:
    recording = _recording_for_member(db, recording_id, actor)
    if recording.status != "ready" or not recording.duration_ms:
        raise HTTPException(status_code=409, detail="Kayıt henüz probe edilip hazır olmadı")
    if payload.offset_ms > recording.duration_ms:
        raise HTTPException(status_code=422, detail="Marker kayıt süresinin dışında")
    existing = (
        db.query(HighlightMarker)
        .filter(
            HighlightMarker.recording_id == recording.id,
            HighlightMarker.external_marker_id == payload.marker_id,
        )
        .first()
    )
    if existing and existing.candidate:
        return existing.candidate
    server = db.get(Server, recording.server_id)
    if not set(payload.participant_player_ids).issubset(_server_user_ids(db, server)):
        raise HTTPException(status_code=422, detail="Marker yalnızca sunucu oyuncularını içerebilir")
    category = payload.category_hint or "COMEDY"
    pre_ms, post_ms = PADDING[category]
    start_ms = max(0, payload.offset_ms - pre_ms)
    end_ms = min(recording.duration_ms, payload.offset_ms + post_ms)
    if end_ms - start_ms < 1_000:
        raise HTTPException(status_code=422, detail="Marker etrafında yeterli video yok")
    raw_score = (
        0.20 * payload.manual_priority
        + 0.12 * (payload.commentator_priority or 0)
        + 0.12 * (payload.game_event_severity or 0)
        + 0.06
        + 0.03
    )
    score = round(max(0.45 if payload.manual_priority else 0.0, min(1.0, raw_score)), 4)
    marker = HighlightMarker(
        recording_id=recording.id,
        created_by_id=actor.id,
        external_marker_id=payload.marker_id,
        source_type=payload.source,
        offset_ms=payload.offset_ms,
        category_hint=category,
        participant_player_ids=payload.participant_player_ids,
        summary=payload.summary,
        manual_priority=payload.manual_priority,
        commentator_priority=payload.commentator_priority,
        game_event_severity=payload.game_event_severity,
    )
    db.add(marker)
    db.flush()
    neutral_title = (payload.summary or "İşaretlenen oyun anı")[:120]
    candidate = HighlightCandidate(
        recording_id=recording.id,
        marker_id=marker.id,
        start_ms=start_ms,
        end_ms=end_ms,
        anchor_ms=payload.offset_ms,
        score=score,
        primary_category=category,
        title=neutral_title,
        description="Oyuncunun işaretlediği doğrulanmış kayıt aralığı.",
        participant_player_ids=payload.participant_player_ids,
        signal_scores={
            "manual_marker": payload.manual_priority,
            "commentator_priority": payload.commentator_priority or 0,
            "game_event_severity": payload.game_event_severity or 0,
            "uniqueness": 1,
            "duration_suitability": 1,
        },
        lore_candidate=category == "LORE_WORTHY",
        meme_candidate=category in {"COMEDY", "FAILURE", "CHAOS"},
    )
    db.add(candidate)
    db.flush()
    enqueue_job(
        db,
        module="highlight_generator",
        job_type="highlight.metadata",
        idempotency_key=f"metadata:{candidate.id}",
        input_ref={"candidate_id": candidate.id},
        session_id=recording.session_id,
        actor_id=actor.id,
        priority=3,
    )
    add_outbox_event(
        db,
        topic="highlight_generator.events",
        aggregate_type="highlight_candidate",
        aggregate_id=candidate.id,
        event_type="highlight.candidate_proposed",
        payload={"candidate_id": candidate.id, "recording_id": recording.id, "score": score},
    )
    db.commit()
    return db.get(HighlightCandidate, candidate.id)


def candidate_to_dict(candidate: HighlightCandidate) -> dict:
    return {
        "id": candidate.id,
        "recording_id": candidate.recording_id,
        "marker_id": candidate.marker_id,
        "start_ms": candidate.start_ms,
        "end_ms": candidate.end_ms,
        "anchor_ms": candidate.anchor_ms,
        "score": candidate.score,
        "primary_category": candidate.primary_category,
        "title": candidate.title,
        "description": candidate.description,
        "participant_player_ids": candidate.participant_player_ids,
        "status": candidate.status.upper(),
    }


def queue_render(
    db: Session,
    *,
    candidate_id: str,
    actor: User,
    payload: RenderHighlightCreate,
) -> RenderedHighlight:
    candidate = db.get(HighlightCandidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Highlight adayı bulunamadı")
    recording = _recording_for_member(db, candidate.recording_id, actor)
    start_ms = payload.start_ms if payload.start_ms is not None else candidate.start_ms
    end_ms = payload.end_ms if payload.end_ms is not None else candidate.end_ms
    if start_ms >= end_ms or end_ms > (recording.duration_ms or 0) or end_ms - start_ms > 60_000:
        raise HTTPException(status_code=422, detail="Trim aralığı geçersiz")
    existing = (
        db.query(RenderedHighlight)
        .filter(RenderedHighlight.candidate_id == candidate.id, RenderedHighlight.variant == payload.variant.lower())
        .first()
    )
    if existing:
        return existing
    highlight = RenderedHighlight(
        candidate_id=candidate.id,
        server_id=recording.server_id,
        session_id=recording.session_id,
        created_by_id=actor.id,
        variant=payload.variant.lower(),
        title=payload.title_override or candidate.title,
        description=payload.description_override if payload.description_override is not None else candidate.description,
        start_ms=start_ms,
        end_ms=end_ms,
        duration_ms=end_ms - start_ms,
        render_parameters={"normalize_audio": True, "render_version": "ffmpeg-v1"},
    )
    db.add(highlight)
    db.flush()
    job = enqueue_job(
        db,
        module="highlight_generator",
        job_type="highlight.render",
        idempotency_key=f"render:{highlight.id}:{start_ms}:{end_ms}:landscape",
        input_ref={"highlight_id": highlight.id},
        session_id=recording.session_id,
        actor_id=actor.id,
        priority=5,
    )
    highlight.render_job_id = job.id
    candidate.status = "rendering"
    db.commit()
    return db.get(RenderedHighlight, highlight.id)


def rendered_to_dict(db: Session, highlight: RenderedHighlight) -> dict:
    candidate = db.get(HighlightCandidate, highlight.candidate_id)
    return {
        "id": highlight.id,
        "candidate_id": highlight.candidate_id,
        "status": highlight.status.upper(),
        "category": candidate.primary_category,
        "variant": highlight.variant.upper(),
        "title": highlight.title,
        "description": highlight.description,
        "video_url": f"/highlight/assets/{highlight.video_asset_id}" if highlight.video_asset_id else None,
        "thumbnail_url": f"/highlight/assets/{highlight.thumbnail_asset_id}" if highlight.thumbnail_asset_id else None,
        "duration_ms": highlight.duration_ms,
        "width": highlight.width,
        "height": highlight.height,
        "error_code": highlight.error_code,
        "created_at": highlight.created_at,
    }


def resolve_asset(db: Session, *, asset_id: str, actor: User) -> tuple[MediaAsset, Path]:
    asset = db.get(MediaAsset, asset_id)
    if not asset or asset.kind not in {"highlight_recording", "highlight_video", "highlight_thumbnail"} or asset.status != "active":
        raise HTTPException(status_code=404, detail="Highlight dosyası bulunamadı")
    _server_for_member(db, asset.server_id, actor)
    root = Path(settings.highlight_media_dir).resolve()
    path = (root / asset.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Highlight dosyası bulunamadı")
    return asset, path


def submit_feedback(db: Session, *, highlight_id: str, actor: User, payload: HighlightFeedbackCreate) -> HighlightFeedback:
    highlight = db.get(RenderedHighlight, highlight_id)
    if not highlight or highlight.deleted_at:
        raise HTTPException(status_code=404, detail="Highlight bulunamadı")
    _server_for_member(db, highlight.server_id, actor)
    row = db.query(HighlightFeedback).filter_by(highlight_id=highlight.id, user_id=actor.id).first()
    if row is None:
        row = HighlightFeedback(highlight_id=highlight.id, user_id=actor.id)
        db.add(row)
    row.feedback_type = payload.feedback_type
    row.details = payload.details
    db.commit()
    return row
