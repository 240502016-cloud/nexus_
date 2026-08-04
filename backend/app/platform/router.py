from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import SessionLocal, get_db
from app.platform import schemas
from app.platform.events import event_is_visible, serialize_event
from app.platform.models import ExperienceEvent
from app.platform.sessions import (
    _get_session,
    consume_ws_ticket,
    create_session,
    ensure_session_access,
    ensure_session_player,
    issue_ws_ticket,
    join_session,
    session_to_dict,
    set_ready,
    start_session,
)


router = APIRouter(tags=["experiences"])


@router.post(
    "/servers/{server_id}/experiences",
    response_model=schemas.ExperienceRead,
    status_code=201,
)
def create_experience(
    server_id: int,
    payload: schemas.ExperienceCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = create_session(
        db,
        server_id=server_id,
        module_type=payload.module_type,
        owner=current_user,
        idempotency_key=idempotency_key,
        channel_id=payload.channel_id,
        settings=payload.settings,
    )
    return session_to_dict(session)


@router.get("/experiences/{session_id}", response_model=schemas.ExperienceRead)
def get_experience(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id)
    ensure_session_access(db, session, current_user)
    ensure_session_player(db, session, current_user.id)
    return session_to_dict(session)


@router.post("/experiences/{session_id}/join", response_model=schemas.ExperienceRead)
def join_experience(
    session_id: str,
    payload: schemas.RevisionCommand,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return session_to_dict(join_session(db, session_id, current_user, payload.expected_revision))


@router.post("/experiences/{session_id}/ready", response_model=schemas.ExperienceRead)
def ready_experience(
    session_id: str,
    payload: schemas.ReadyCommand,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return session_to_dict(
        set_ready(db, session_id, current_user, payload.expected_revision, payload.ready)
    )


@router.post("/experiences/{session_id}/start", response_model=schemas.ExperienceRead)
def start_experience(
    session_id: str,
    payload: schemas.RevisionCommand,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return session_to_dict(start_session(db, session_id, current_user, payload.expected_revision))


@router.get("/experiences/{session_id}/events", response_model=schemas.ExperienceEventPage)
def list_experience_events(
    session_id: str,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id)
    ensure_session_access(db, session, current_user)
    ensure_session_player(db, session, current_user.id)
    events = (
        db.query(ExperienceEvent)
        .filter(ExperienceEvent.session_id == session_id, ExperienceEvent.sequence > after)
        .order_by(ExperienceEvent.sequence)
        .limit(limit)
        .all()
    )
    visible = [serialize_event(event) for event in events if event_is_visible(event, current_user.id)]
    # Advance over every scanned row, including events for another private audience.
    # Otherwise a client can poll the same invisible row forever and later public events
    # can be starved behind the page limit.
    return {"items": visible, "last_sequence": events[-1].sequence if events else after}


@router.post("/experiences/{session_id}/ws-ticket", response_model=schemas.WsTicketRead)
def create_experience_ws_ticket(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id)
    ticket, expires_at = issue_ws_ticket(db, session, current_user)
    return {"ticket": ticket, "expires_at": expires_at}


def _poll_visible_events(session_id: str, user_id: int, after: int) -> tuple[list[dict], int]:
    db = SessionLocal()
    try:
        events = (
            db.query(ExperienceEvent)
            .filter(ExperienceEvent.session_id == session_id, ExperienceEvent.sequence > after)
            .order_by(ExperienceEvent.sequence)
            .limit(500)
            .all()
        )
        visible = [
            schemas.ExperienceEventRead(**serialize_event(event)).model_dump(mode="json")
            for event in events
            if event_is_visible(event, user_id)
        ]
        return visible, events[-1].sequence if events else after
    finally:
        db.close()


@router.websocket("/experiences/{session_id}/ws")
async def experience_socket(
    websocket: WebSocket,
    session_id: str,
    ticket: str = Query(..., min_length=32, max_length=256),
    after: int = Query(default=0, ge=0),
):
    db = SessionLocal()
    try:
        user_id = consume_ws_ticket(db, session_id, ticket)
        if user_id is None:
            await websocket.close(code=4401)
            return
        session = _get_session(db, session_id)
        user = db.get(User, user_id)
        if user is None:
            await websocket.close(code=4401)
            return
        ensure_session_access(db, session, user)
        ensure_session_player(db, session, user.id)
        snapshot = schemas.ExperienceRead(**session_to_dict(session)).model_dump(mode="json")
    except HTTPException as exc:
        await websocket.close(code=4404 if exc.status_code == 404 else 4403)
        return
    finally:
        db.close()

    await websocket.accept()
    await websocket.send_json({"type": "session.snapshot", "payload": snapshot})
    last_sequence = after
    try:
        while True:
            events, scanned_sequence = await asyncio.to_thread(
                _poll_visible_events,
                session_id,
                user_id,
                last_sequence,
            )
            for event in events:
                await websocket.send_json(event)
            last_sequence = max(last_sequence, scanned_sequence)
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "hello":
                requested = message.get("last_sequence")
                if isinstance(requested, int) and requested >= 0:
                    last_sequence = requested
    except WebSocketDisconnect:
        return
