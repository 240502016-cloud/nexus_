from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.database import get_db
from app.modules.ai_commentator import schemas
from app.modules.ai_commentator.service import (
    _commentator_session,
    create_commentary_session,
    end_commentary_session,
    find_active_commentary_session,
    get_history,
    ingest_event,
    list_profiles,
    session_to_dict,
    submit_feedback,
    update_commentary_session,
    update_preference,
)
from app.platform.sessions import ensure_session_access, ensure_session_player


router = APIRouter(tags=["ai-commentator"])


@router.get(
    "/servers/{server_id}/commentary/profiles",
    response_model=list[schemas.CommentatorProfileRead],
)
def get_commentator_profiles(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, current_user)
    return list_profiles()


@router.post(
    "/servers/{server_id}/commentary/sessions",
    response_model=schemas.CommentarySessionRead,
    status_code=201,
)
def start_commentary_session(
    server_id: int,
    payload: schemas.CommentarySessionCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = create_commentary_session(
        db,
        server_id=server_id,
        actor=current_user,
        payload=payload,
        idempotency_key=idempotency_key,
    )
    return session_to_dict(session)


@router.get(
    "/servers/{server_id}/commentary/sessions/active",
    response_model=schemas.CommentarySessionRead | None,
)
def get_active_commentary_session(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = find_active_commentary_session(db, server_id=server_id, actor=current_user)
    return session_to_dict(session) if session else None


@router.get(
    "/commentary/sessions/{session_id}",
    response_model=schemas.CommentarySessionRead,
)
def get_commentary_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _commentator_session(db, session_id)
    ensure_session_access(db, session, current_user)
    ensure_session_player(db, session, current_user.id)
    return session_to_dict(session)


@router.patch(
    "/commentary/sessions/{session_id}",
    response_model=schemas.CommentarySessionRead,
)
def patch_commentary_session(
    session_id: str,
    payload: schemas.CommentarySessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return session_to_dict(
        update_commentary_session(db, session_id=session_id, actor=current_user, payload=payload)
    )


@router.post(
    "/commentary/sessions/{session_id}/events",
    response_model=schemas.PostEventResponse,
    status_code=202,
)
def post_commentator_event(
    session_id: str,
    payload: schemas.CommentatorEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    event, state = ingest_event(db, session_id=session_id, actor=current_user, payload=payload)
    return {"event_id": event.external_event_id, "accepted": True, "state": state}


@router.get(
    "/commentary/sessions/{session_id}/history",
    response_model=schemas.CommentaryHistoryRead,
)
def get_commentator_history(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_history(db, session_id=session_id, actor=current_user, limit=limit)


@router.post(
    "/commentary/commentary/{commentary_id}/feedback",
    response_model=schemas.CommentaryFeedbackRead,
)
def post_commentary_feedback(
    commentary_id: str,
    payload: schemas.CommentaryFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return submit_feedback(
        db,
        commentary_id=commentary_id,
        actor=current_user,
        feedback_type=payload.feedback_type,
        details=payload.details,
    )


@router.post(
    "/commentary/sessions/{session_id}/end",
    response_model=schemas.CommentarySessionRead,
)
def stop_commentary_session(
    session_id: str,
    payload: schemas.CommentarySessionEnd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = end_commentary_session(
        db,
        session_id=session_id,
        actor=current_user,
        expected_revision=payload.expected_revision,
    )
    return session_to_dict(session)


@router.put(
    "/servers/{server_id}/commentary/preferences/me",
    response_model=schemas.CommentatorPreferenceRead,
)
def put_commentator_preferences(
    server_id: int,
    payload: schemas.CommentatorPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_preference(db, server_id=server_id, actor=current_user, payload=payload)
