from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.platform.models import ExperienceEvent, ExperienceSession, OutboxEvent


def add_outbox_event(
    db: Session,
    *,
    topic: str,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    schema_version: int = 1,
) -> OutboxEvent:
    """Add a domain event to the caller's transaction."""
    event = OutboxEvent(
        topic=topic,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        schema_version=schema_version,
        payload=payload,
    )
    db.add(event)
    return event


def append_event(
    db: Session,
    session: ExperienceSession,
    event_type: str,
    payload: dict,
    *,
    audience: str = "PUBLIC",
    idempotency_key: str | None = None,
) -> ExperienceEvent:
    """Append a replay event and matching outbox record in the caller's transaction."""
    if idempotency_key:
        existing = (
            db.query(ExperienceEvent)
            .filter(
                ExperienceEvent.session_id == session.id,
                ExperienceEvent.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return existing

    last_sequence = (
        db.query(func.max(ExperienceEvent.sequence))
        .filter(ExperienceEvent.session_id == session.id)
        .scalar()
        or 0
    )
    event = ExperienceEvent(
        session_id=session.id,
        sequence=last_sequence + 1,
        revision=session.revision,
        event_type=event_type,
        audience=audience,
        public_payload=payload,
        idempotency_key=idempotency_key,
    )
    db.add(event)
    add_outbox_event(
        db,
        topic="experience.events",
        aggregate_type="experience_session",
        aggregate_id=session.id,
        event_type=event_type,
        payload={
            "session_id": session.id,
            "sequence": event.sequence,
            "revision": session.revision,
            "audience": audience,
            "payload": payload,
        },
    )
    db.flush()
    return event


def event_is_visible(event: ExperienceEvent, user_id: int) -> bool:
    return event.audience == "PUBLIC" or event.audience == f"USER:{user_id}"


def serialize_event(event: ExperienceEvent) -> dict:
    return {
        "id": event.id,
        "type": event.event_type,
        "schema_version": event.schema_version,
        "session_id": event.session_id,
        "sequence": event.sequence,
        "revision": event.revision,
        "audience": event.audience,
        "occurred_at": event.created_at,
        "payload": event.public_payload,
    }
