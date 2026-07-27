from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.matrix_client import MatrixError, matrix_client
from app.core.matrix_rooms import invite_and_join, is_not_in_room_error, repair_room_membership
from app.core.models import Friendship, User
from app.core.routers.gateway import notify_direct_message
from app.database import get_db

router = APIRouter(prefix="/direct", tags=["direct-messages"])


def _public(user: User) -> schemas.PublicUserRead:
    return schemas.PublicUserRead.model_validate(user)


def _get_conversation(db: Session, conversation_id: int, user_id: int) -> Friendship:
    friendship = db.get(Friendship, conversation_id)
    if (
        not friendship
        or friendship.status != "accepted"
        or user_id not in (friendship.user_low_id, friendship.user_high_id)
    ):
        raise HTTPException(status_code=404, detail="Özel konuşma bulunamadı")
    return friendship


def _ensure_room(db: Session, friendship: Friendship, current_user: User) -> str:
    if friendship.matrix_room_id:
        return friendship.matrix_room_id
    friend = friendship.other_user(current_user.id)
    if not current_user.matrix_access_token or not friend.matrix_access_token:
        raise HTTPException(status_code=409, detail="Özel mesaj için Matrix hesabı eksik")
    try:
        room_id = matrix_client.create_room(current_user.matrix_access_token, "Nexus · Özel Mesaj")
        invite_and_join(room_id, current_user, friend)
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=f"Özel mesaj odası oluşturulamadı: {exc}") from exc
    friendship.matrix_room_id = room_id
    friendship.matrix_owner_id = current_user.id
    db.add(friendship)
    db.commit()
    return room_id


def _repair(friendship: Friendship, current_user: User) -> None:
    owner = friendship.matrix_owner
    if not friendship.matrix_room_id or not owner:
        raise MatrixError("Özel mesaj odasının sahibi bulunamadı")
    repair_room_membership(friendship.matrix_room_id, owner, current_user)


@router.get("/conversations", response_model=list[schemas.DirectConversationRead])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendships = (
        db.query(Friendship)
        .filter(
            Friendship.status == "accepted",
            or_(
                Friendship.user_low_id == current_user.id,
                Friendship.user_high_id == current_user.id,
            ),
        )
        .order_by(Friendship.updated_at.desc())
        .all()
    )
    return [
        schemas.DirectConversationRead(
            id=item.id,
            friend=_public(item.other_user(current_user.id)),
            created_at=item.updated_at,
        )
        for item in friendships
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=schemas.MessagePage)
def list_direct_messages(
    conversation_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendship = _get_conversation(db, conversation_id, current_user.id)
    if not friendship.matrix_room_id:
        return schemas.MessagePage(items=[], next_cursor=None, has_more=False)
    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")
    try:
        return matrix_client.get_message_page(
            current_user.matrix_access_token,
            friendship.matrix_room_id,
            limit=limit,
            cursor=cursor,
        )
    except MatrixError as exc:
        if not is_not_in_room_error(exc):
            raise HTTPException(
                status_code=502,
                detail="Özel mesaj geçmişi geçici olarak yüklenemiyor; lütfen tekrar deneyin",
            ) from exc
        try:
            _repair(friendship, current_user)
            return matrix_client.get_message_page(
                current_user.matrix_access_token,
                friendship.matrix_room_id,
                limit=limit,
                cursor=cursor,
            )
        except MatrixError as retry_exc:
            raise HTTPException(
                status_code=502,
                detail="Özel mesaj üyeliği otomatik onarılamadı; lütfen tekrar deneyin",
            ) from retry_exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=schemas.MessageRead,
    status_code=201,
)
def send_direct_message(
    conversation_id: int,
    payload: schemas.MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendship = _get_conversation(db, conversation_id, current_user.id)
    room_id = _ensure_room(db, friendship, current_user)
    if not current_user.matrix_access_token or not current_user.matrix_user_id:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")
    try:
        event_id = matrix_client.send_message(
            current_user.matrix_access_token,
            room_id,
            payload.content,
            txn_id=payload.client_id or uuid.uuid4().hex,
        )
    except MatrixError as exc:
        if not is_not_in_room_error(exc):
            raise HTTPException(
                status_code=502,
                detail="Özel mesaj servisi geçici olarak kullanılamıyor; lütfen tekrar deneyin",
            ) from exc
        try:
            _repair(friendship, current_user)
            event_id = matrix_client.send_message(
                current_user.matrix_access_token,
                room_id,
                payload.content,
                txn_id=payload.client_id or uuid.uuid4().hex,
            )
        except MatrixError as retry_exc:
            raise HTTPException(
                status_code=502,
                detail="Özel mesaj üyeliği otomatik onarılamadı; lütfen tekrar deneyin",
            ) from retry_exc

    message = schemas.MessageRead(
        event_id=event_id,
        sender=current_user.matrix_user_id,
        content=payload.content,
        client_id=payload.client_id,
    )
    friend = friendship.other_user(current_user.id)
    notify_direct_message(
        friendship.id,
        {current_user.id, friend.id},
        current_user.id,
        message.model_dump(),
    )
    return message


@router.patch(
    "/conversations/{conversation_id}/messages/{event_id}",
    response_model=schemas.MessageRead,
)
def edit_direct_message(
    conversation_id: int,
    event_id: str,
    payload: schemas.MessageEdit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendship = _get_conversation(db, conversation_id, current_user.id)
    if (
        not friendship.matrix_room_id
        or not current_user.matrix_access_token
        or not current_user.matrix_user_id
    ):
        raise HTTPException(status_code=409, detail="Özel mesaj odası hazır değil")
    try:
        original = matrix_client.get_event(
            current_user.matrix_access_token, friendship.matrix_room_id, event_id
        )
        if original.get("sender") != current_user.matrix_user_id:
            raise HTTPException(status_code=403, detail="Yalnızca kendi mesajınızı düzenleyebilirsiniz")
        matrix_client.edit_message(
            current_user.matrix_access_token,
            friendship.matrix_room_id,
            event_id,
            payload.content,
        )
    except HTTPException:
        raise
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    message = schemas.MessageRead(
        event_id=event_id,
        sender=current_user.matrix_user_id,
        content=payload.content,
        edited=True,
    )
    friend = friendship.other_user(current_user.id)
    notify_direct_message(
        friendship.id,
        {current_user.id, friend.id},
        current_user.id,
        message.model_dump(),
    )
    return message
