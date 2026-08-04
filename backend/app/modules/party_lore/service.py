from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import ensure_server_member
from app.core.models import Server, ServerMember, User
from app.modules.party_lore.models import (
    LoreCandidate,
    LoreCandidateParticipant,
    LoreEntry,
    LoreEvidence,
    LoreParticipant,
    LoreUsage,
)
from app.modules.party_lore.schemas import LoreCandidateCreate, LoreRetrieve
from app.platform.events import add_outbox_event
from app.platform.models import utcnow
from app.platform.sessions import SUPPORTED_MODULES


SENSITIVITY_LEVELS = {"low", "medium", "high"}


def _server_for_member(db: Session, server_id: int, user: User) -> Server:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, user)
    return server


def _candidate(db: Session, candidate_id: str, *, lock: bool = False) -> LoreCandidate:
    query = db.query(LoreCandidate).filter(LoreCandidate.id == candidate_id)
    if lock:
        query = query.with_for_update()
    candidate = query.first()
    if not candidate:
        raise HTTPException(status_code=404, detail="Lore adayı bulunamadı")
    return candidate


def _entry(db: Session, lore_id: str, *, lock: bool = False) -> LoreEntry:
    query = db.query(LoreEntry).filter(LoreEntry.id == lore_id)
    if lock:
        query = query.with_for_update()
    entry = query.first()
    if not entry:
        raise HTTPException(status_code=404, detail="Lore kaydı bulunamadı")
    return entry


def _ensure_candidate_visible(candidate: LoreCandidate, user_id: int) -> None:
    participant_ids = {participant.user_id for participant in candidate.participants}
    if candidate.submitted_by_id != user_id and user_id not in participant_ids:
        raise HTTPException(status_code=403, detail="Bu lore adayını görüntüleyemezsiniz")


def get_candidate_for_user(db: Session, *, candidate_id: str, actor: User) -> LoreCandidate:
    candidate = _candidate(db, candidate_id)
    _server_for_member(db, candidate.server_id, actor)
    _ensure_candidate_visible(candidate, actor.id)
    return candidate


def candidate_to_dict(candidate: LoreCandidate) -> dict:
    return {
        "id": candidate.id,
        "server_id": candidate.server_id,
        "submitted_by_id": candidate.submitted_by_id,
        "title": candidate.title,
        "summary": candidate.summary,
        "category": candidate.category,
        "sensitivity": candidate.sensitivity,
        "allowed_modules": candidate.allowed_modules,
        "status": candidate.status,
        "participants": [
            {
                "user_id": participant.user_id,
                "decision": participant.decision,
                "decided_at": participant.decided_at,
            }
            for participant in candidate.participants
        ],
        "lore_id": candidate.entry.id if candidate.entry else None,
        "created_at": candidate.created_at,
        "reviewed_at": candidate.reviewed_at,
    }


def entry_to_dict(entry: LoreEntry) -> dict:
    return {
        "id": entry.id,
        "server_id": entry.server_id,
        "title": entry.title,
        "summary": entry.summary,
        "category": entry.category,
        "sensitivity": entry.sensitivity,
        "allowed_modules": entry.allowed_modules,
        "participant_ids": [participant.user_id for participant in entry.participants],
        "status": entry.status,
        "version": entry.version,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }


def create_candidate(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: LoreCandidateCreate,
    idempotency_key: str,
) -> LoreCandidate:
    _server_for_member(db, server_id, actor)
    if payload.sensitivity not in SENSITIVITY_LEVELS:
        raise HTTPException(status_code=422, detail="Geçersiz hassasiyet seviyesi")
    invalid_modules = set(payload.allowed_modules) - SUPPORTED_MODULES
    if invalid_modules:
        raise HTTPException(status_code=422, detail="Geçersiz Party Lore kullanım modülü")

    existing = (
        db.query(LoreCandidate)
        .filter(
            LoreCandidate.server_id == server_id,
            LoreCandidate.submitted_by_id == actor.id,
            LoreCandidate.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return existing

    member_ids = {
        row[0]
        for row in db.query(ServerMember.user_id)
        .filter(
            ServerMember.server_id == server_id,
            ServerMember.user_id.in_(payload.participant_ids),
        )
        .all()
    }
    if member_ids != set(payload.participant_ids):
        raise HTTPException(status_code=422, detail="Tüm lore katılımcıları sunucu üyesi olmalı")

    candidate = LoreCandidate(
        server_id=server_id,
        submitted_by_id=actor.id,
        idempotency_key=idempotency_key,
        title=payload.title,
        summary=payload.summary,
        category=payload.category,
        sensitivity=payload.sensitivity,
        allowed_modules=sorted(set(payload.allowed_modules)),
    )
    db.add(candidate)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(LoreCandidate)
            .filter(
                LoreCandidate.server_id == server_id,
                LoreCandidate.submitted_by_id == actor.id,
                LoreCandidate.idempotency_key == idempotency_key,
            )
            .first()
        )
        if concurrent:
            return concurrent
        raise
    for user_id in sorted(member_ids):
        db.add(LoreCandidateParticipant(candidate_id=candidate.id, user_id=user_id))
    add_outbox_event(
        db,
        topic="party_lore.events",
        aggregate_type="lore_candidate",
        aggregate_id=candidate.id,
        event_type="party_lore.candidate_created",
        payload={"candidate_id": candidate.id, "server_id": server_id},
    )
    db.commit()
    return _candidate(db, candidate.id)


def list_candidates(
    db: Session,
    *,
    server_id: int,
    actor: User,
    status: str | None = None,
) -> list[LoreCandidate]:
    _server_for_member(db, server_id, actor)
    query = (
        db.query(LoreCandidate)
        .outerjoin(LoreCandidateParticipant)
        .filter(
            LoreCandidate.server_id == server_id,
            or_(
                LoreCandidate.submitted_by_id == actor.id,
                LoreCandidateParticipant.user_id == actor.id,
            ),
        )
    )
    if status:
        query = query.filter(LoreCandidate.status == status)
    return query.distinct().order_by(LoreCandidate.created_at.desc()).all()


def review_candidate(
    db: Session,
    *,
    candidate_id: str,
    actor: User,
    decision: str,
) -> LoreCandidate:
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Karar approved veya rejected olmalı")
    candidate = _candidate(db, candidate_id, lock=True)
    _server_for_member(db, candidate.server_id, actor)
    participant = db.get(
        LoreCandidateParticipant,
        {"candidate_id": candidate.id, "user_id": actor.id},
    )
    if not participant:
        raise HTTPException(status_code=403, detail="Yalnızca lore katılımcıları karar verebilir")
    if candidate.status != "pending":
        return candidate
    if participant.decision == decision:
        return candidate

    participant.decision = decision
    participant.decided_at = utcnow()
    if decision == "rejected":
        candidate.status = "rejected"
        candidate.reviewed_at = utcnow()
        event_type = "party_lore.candidate_rejected"
    else:
        db.flush()
        all_approved = all(item.decision == "approved" for item in candidate.participants)
        event_type = "party_lore.candidate_approved"
        if all_approved:
            candidate.status = "confirmed"
            candidate.reviewed_at = utcnow()
            entry = LoreEntry(
                candidate_id=candidate.id,
                server_id=candidate.server_id,
                created_by_id=candidate.submitted_by_id,
                title=candidate.title,
                summary=candidate.summary,
                category=candidate.category,
                sensitivity=candidate.sensitivity,
                allowed_modules=candidate.allowed_modules,
            )
            db.add(entry)
            db.flush()
            for item in candidate.participants:
                db.add(LoreParticipant(lore_id=entry.id, user_id=item.user_id))
            db.add(
                LoreEvidence(
                    lore_id=entry.id,
                    source_type="manual_candidate",
                    source_ref={"candidate_id": candidate.id},
                )
            )
            event_type = "party_lore.entry_confirmed"

    add_outbox_event(
        db,
        topic="party_lore.events",
        aggregate_type="lore_candidate",
        aggregate_id=candidate.id,
        event_type=event_type,
        payload={
            "candidate_id": candidate.id,
            "server_id": candidate.server_id,
            "actor_id": actor.id,
            "status": candidate.status,
        },
    )
    db.commit()
    return _candidate(db, candidate.id)


def list_entries(db: Session, *, server_id: int, actor: User) -> list[LoreEntry]:
    _server_for_member(db, server_id, actor)
    entries = (
        db.query(LoreEntry)
        .filter(LoreEntry.server_id == server_id, LoreEntry.status == "active")
        .order_by(LoreEntry.created_at.desc())
        .all()
    )
    return [
        entry
        for entry in entries
        if entry.sensitivity != "high"
        or actor.id in {participant.user_id for participant in entry.participants}
    ]


def find_entries(
    db: Session,
    *,
    server_id: int,
    actor: User,
    module: str,
    query: str = "",
    participant_ids: list[int] | None = None,
    limit: int = 5,
    excluded_lore_ids: set[str] | None = None,
) -> list[LoreEntry]:
    _server_for_member(db, server_id, actor)
    if module not in SUPPORTED_MODULES:
        raise HTTPException(status_code=422, detail="Geçersiz Party Lore kullanım modülü")

    entries = (
        db.query(LoreEntry)
        .filter(
            LoreEntry.server_id == server_id,
            LoreEntry.status == "active",
            LoreEntry.sensitivity.in_(["low", "medium"]),
        )
        .order_by(LoreEntry.created_at.desc())
        .limit(200)
        .all()
    )
    participant_filter = set(participant_ids or [])
    excluded = excluded_lore_ids or set()
    tokens = {token for token in re.findall(r"[\w]+", query.casefold()) if len(token) > 1}
    scored: list[tuple[int, LoreEntry]] = []
    for entry in entries:
        if entry.id in excluded or module not in entry.allowed_modules:
            continue
        entry_participants = {participant.user_id for participant in entry.participants}
        if participant_filter and not entry_participants.intersection(participant_filter):
            continue
        if any(participant.consent_state != "confirmed" for participant in entry.participants):
            continue
        haystack = f"{entry.title} {entry.summary} {entry.category}".casefold()
        score = sum(1 for token in tokens if token in haystack)
        if tokens and score == 0:
            continue
        scored.append((score, entry))

    selected = [entry for _, entry in sorted(scored, key=lambda item: item[0], reverse=True)][
        : max(1, min(limit, 10))
    ]
    return selected


def record_lore_usage(
    db: Session,
    *,
    entry: LoreEntry,
    actor: User,
    module: str,
    request_id: str,
    context: dict | None = None,
) -> LoreUsage:
    existing = (
        db.query(LoreUsage)
        .filter(LoreUsage.request_id == request_id, LoreUsage.lore_id == entry.id)
        .first()
    )
    if existing:
        return existing
    usage = LoreUsage(
        request_id=request_id,
        lore_id=entry.id,
        server_id=entry.server_id,
        actor_id=actor.id,
        module=module,
        context=context or {},
    )
    db.add(usage)
    return usage


def retrieve_entries(
    db: Session,
    *,
    server_id: int,
    actor: User,
    payload: LoreRetrieve,
) -> list[LoreEntry]:
    selected = find_entries(
        db,
        server_id=server_id,
        actor=actor,
        module=payload.module,
        query=payload.query,
        participant_ids=payload.participant_ids,
        limit=payload.limit,
    )
    for entry in selected:
        record_lore_usage(
            db,
            entry=entry,
            actor=actor,
            module=payload.module,
            request_id=payload.request_id,
            context={"participant_ids": payload.participant_ids},
        )
    db.commit()
    return selected


def delete_entry(db: Session, *, lore_id: str, actor: User) -> None:
    entry = _entry(db, lore_id, lock=True)
    _server_for_member(db, entry.server_id, actor)
    participant_ids = {participant.user_id for participant in entry.participants}
    if actor.id not in participant_ids:
        raise HTTPException(status_code=403, detail="Lore kaydını yalnızca bir katılımcı silebilir")
    if entry.status == "deleted":
        return
    entry.status = "deleted"
    entry.deleted_at = utcnow()
    entry.version += 1
    add_outbox_event(
        db,
        topic="party_lore.events",
        aggregate_type="lore_entry",
        aggregate_id=entry.id,
        event_type="party_lore.entry_deleted",
        payload={"lore_id": entry.id, "server_id": entry.server_id, "actor_id": actor.id},
    )
    db.commit()
