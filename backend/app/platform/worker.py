from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import and_, or_, select

from app.config import settings
from app.database import SessionLocal
from app.modules.ai_commentator.worker import process_commentator_job
from app.modules.meme_generator.worker import process_meme_job
from app.modules.highlight_generator.metadata_worker import process_highlight_metadata_job
from app.modules.ai_roast_battle.worker import process_roast_job
from app.modules.ai_board_game.worker import process_board_narration_job
from app.modules.hidden_role_game.worker import process_hidden_recap_job
from app.modules.shared_story.worker import process_story_job
from app.modules.ai_escape_room.worker import process_escape_host_job
from app.platform.models import BackgroundJob, utcnow


logger = logging.getLogger("nexus.platform_worker")
WORKER_ID = f"platform-worker-{uuid.uuid4()}"

JobHandler = Callable[[str], dict]
HANDLERS: dict[tuple[str, str], JobHandler] = {
    ("ai_commentator", "commentary.generate"): process_commentator_job,
    ("meme_generator", "meme.caption"): process_meme_job,
    ("highlight_generator", "highlight.metadata"): process_highlight_metadata_job,
    ("ai_roast_battle", "roast.generate_review"): process_roast_job,
    ("ai_board_game", "board.narrate"): process_board_narration_job,
    ("hidden_role_game", "hidden.end_recap"): process_hidden_recap_job,
    ("shared_story", "story.scene_write"): process_story_job,
    ("shared_story", "story.ending_write"): process_story_job,
    ("ai_escape_room", "escape.host_message"): process_escape_host_job,
}


def _claim_next_job(
    eligible_handlers: set[tuple[str, str]],
) -> tuple[str, str, str, int] | None:
    db = SessionLocal()
    try:
        now = utcnow()
        handler_filter = or_(
            *[
                and_(BackgroundJob.module == module, BackgroundJob.job_type == job_type)
                for module, job_type in sorted(eligible_handlers)
            ]
        )
        job = db.execute(
            select(BackgroundJob)
            .where(
                handler_filter,
                BackgroundJob.cancel_requested.is_(False),
                or_(
                    and_(BackgroundJob.status == "queued", BackgroundJob.next_attempt_at <= now),
                    and_(
                        BackgroundJob.status == "running",
                        BackgroundJob.lease_expires_at.is_not(None),
                        BackgroundJob.lease_expires_at < now,
                    ),
                ),
            )
            .order_by(BackgroundJob.priority.desc(), BackgroundJob.created_at, BackgroundJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            db.rollback()
            return None
        job.status = "running"
        job.attempts += 1
        job.locked_by = WORKER_ID
        job.lease_expires_at = now + timedelta(seconds=max(5, settings.ai_worker_lease_seconds))
        job.started_at = job.started_at or now
        claimed = (job.id, job.module, job.job_type, job.attempts)
        db.commit()
        return claimed
    finally:
        db.close()


def _finish_job(job_id: str, result: dict) -> None:
    db = SessionLocal()
    try:
        job = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.id == job_id, BackgroundJob.locked_by == WORKER_ID)
            .with_for_update()
            .first()
        )
        if not job:
            return
        job.status = "succeeded"
        job.result = result
        job.completed_at = utcnow()
        job.locked_by = None
        job.lease_expires_at = None
        job.error = None
        db.commit()
    finally:
        db.close()


def _fail_job(job_id: str, attempts: int, exc: Exception, *, permanent: bool = False) -> None:
    db = SessionLocal()
    try:
        job = (
            db.query(BackgroundJob)
            .filter(BackgroundJob.id == job_id, BackgroundJob.locked_by == WORKER_ID)
            .with_for_update()
            .first()
        )
        if not job:
            return
        if not permanent and attempts < max(1, settings.ai_worker_max_attempts):
            job.status = "queued"
            job.next_attempt_at = utcnow() + timedelta(
                seconds=max(0.1, settings.ai_worker_retry_backoff_seconds)
                * (2 ** max(0, attempts - 1))
            )
        else:
            job.status = "failed"
            job.completed_at = utcnow()
        job.error = str(exc)[:1000]
        job.locked_by = None
        job.lease_expires_at = None
        db.commit()
    finally:
        db.close()


def process_one(*, handlers: dict[tuple[str, str], JobHandler] | None = None) -> bool:
    active_handlers = handlers or HANDLERS
    if not active_handlers:
        return False
    claimed = _claim_next_job(set(active_handlers))
    if claimed is None:
        return False
    job_id, module, job_type, attempts = claimed
    handler = active_handlers.get((module, job_type))
    if handler is None:
        _fail_job(job_id, attempts, ValueError(f"Unknown job handler: {module}/{job_type}"), permanent=True)
        return True
    try:
        result = handler(job_id)
        _finish_job(job_id, result)
    except Exception as exc:
        logger.exception("Platform job failed: job_id=%s module=%s type=%s", job_id, module, job_type)
        _fail_job(job_id, attempts, exc)
    return True
