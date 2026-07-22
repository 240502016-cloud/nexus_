from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.bot_engine.dispatcher import MessageEvent, handle_message_event
from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Channel, User
from app.database import get_db

router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["messages"])


@router.post("", response_model=schemas.MessageRead, status_code=201)
def send_message(
    channel_id: int,
    payload: schemas.MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = db.get(Channel, channel_id)
    if not channel or not channel.matrix_room_id:
        raise HTTPException(status_code=404, detail="Kanal veya Matrix odası bulunamadı")
    ensure_server_member(db, channel.server, current_user)

    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    try:
        event_id = matrix_client.send_message(current_user.matrix_access_token, channel.matrix_room_id, payload.content)
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Bot Engine: mesaj bir komutsa (ör. "/sunucu-durumu"), sunucuya eklenmiş botlar
    # ilgili plugin'i çalıştırıp cevabı kendi Matrix hesabıyla aynı odaya yazar.
    handle_message_event(
        db,
        MessageEvent(
            channel=channel, sender_id=current_user.id, sender_username=current_user.username, content=payload.content
        ),
    )

    return schemas.MessageRead(
        event_id=event_id, sender=current_user.matrix_user_id, content=payload.content, origin_server_ts=None
    )


@router.get("", response_model=list[schemas.MessageRead])
def list_messages(
    channel_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = db.get(Channel, channel_id)
    if not channel or not channel.matrix_room_id:
        raise HTTPException(status_code=404, detail="Kanal veya Matrix odası bulunamadı")
    ensure_server_member(db, channel.server, current_user)

    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    try:
        return matrix_client.get_messages(current_user.matrix_access_token, channel.matrix_room_id, limit=limit)
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
