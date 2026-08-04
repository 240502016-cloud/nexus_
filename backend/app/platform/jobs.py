from __future__ import annotations

from sqlalchemy.orm import Session

from app.platform.models import BackgroundJob


def enqueue_job(
    db: Session,
    *,
    module: str,
    job_type: str,
    idempotency_key: str,
    input_ref: dict,
    session_id: str | None = None,
    actor_id: int | None = None,
    priority: int = 0,
) -> BackgroundJob:
    """Create one durable job or return the existing idempotent job."""
    existing = (
        db.query(BackgroundJob)
        .filter(
            BackgroundJob.module == module,
            BackgroundJob.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return existing
    job = BackgroundJob(
        module=module,
        job_type=job_type,
        session_id=session_id,
        actor_id=actor_id,
        input_ref=input_ref,
        idempotency_key=idempotency_key,
        priority=priority,
    )
    db.add(job)
    db.flush()
    return job
