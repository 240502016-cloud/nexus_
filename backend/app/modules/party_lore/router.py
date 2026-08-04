from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.party_lore import schemas
from app.modules.party_lore.service import (
    candidate_to_dict,
    create_candidate,
    delete_entry,
    entry_to_dict,
    get_candidate_for_user,
    list_candidates,
    list_entries,
    retrieve_entries,
    review_candidate,
)


router = APIRouter(tags=["party-lore"])


@router.post(
    "/servers/{server_id}/party-lore/candidates",
    response_model=schemas.LoreCandidateRead,
    status_code=201,
)
def submit_lore_candidate(
    server_id: int,
    payload: schemas.LoreCandidateCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    candidate = create_candidate(
        db,
        server_id=server_id,
        actor=current_user,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return candidate_to_dict(candidate)


@router.get(
    "/servers/{server_id}/party-lore/candidates",
    response_model=list[schemas.LoreCandidateRead],
)
def get_lore_candidates(
    server_id: int,
    status: str | None = Query(default=None, max_length=16),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [
        candidate_to_dict(candidate)
        for candidate in list_candidates(db, server_id=server_id, actor=current_user, status=status)
    ]


@router.get("/party-lore/candidates/{candidate_id}", response_model=schemas.LoreCandidateRead)
def get_lore_candidate(
    candidate_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    candidate = get_candidate_for_user(db, candidate_id=candidate_id, actor=current_user)
    return candidate_to_dict(candidate)


@router.post(
    "/party-lore/candidates/{candidate_id}/review",
    response_model=schemas.LoreCandidateRead,
)
def decide_lore_candidate(
    candidate_id: str,
    payload: schemas.LoreReview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return candidate_to_dict(
        review_candidate(
            db,
            candidate_id=candidate_id,
            actor=current_user,
            decision=payload.decision,
        )
    )


@router.get(
    "/servers/{server_id}/party-lore/entries",
    response_model=list[schemas.LoreEntryRead],
)
def get_lore_entries(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return [
        entry_to_dict(entry)
        for entry in list_entries(db, server_id=server_id, actor=current_user)
    ]


@router.post(
    "/servers/{server_id}/party-lore/retrieve",
    response_model=schemas.LoreRetrieveResult,
)
def retrieve_party_lore(
    server_id: int,
    payload: schemas.LoreRetrieve,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = retrieve_entries(db, server_id=server_id, actor=current_user, payload=payload)
    return {"items": [entry_to_dict(entry) for entry in entries], "request_id": payload.request_id}


@router.delete("/party-lore/entries/{lore_id}", status_code=204)
def remove_lore_entry(
    lore_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_entry(db, lore_id=lore_id, actor=current_user)
    return Response(status_code=204)
