import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.bot_engine.dispatcher import MessageEvent, handle_message_event, is_private_message_event
from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member
from app.core.matrix_client import MatrixError, matrix_client
from app.core.matrix_rooms import is_not_in_room_error, repair_room_membership
from app.core.models import BotServerLink, Channel, ChannelType, User
from app.core.routers.gateway import notify_channel_message
from app.database import get_db

router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["messages"])


def _get_text_channel(db: Session, channel_id: int) -> Channel:
    channel = db.get(Channel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Kanal bulunamadı")
    if channel.type != ChannelType.TEXT:
        raise HTTPException(status_code=409, detail="Ses kanallarının mesaj geçmişi yok")
    if not channel.matrix_room_id:
        raise HTTPException(status_code=404, detail="Kanalın Matrix odası bulunamadı")
    return channel


def _repair_membership(channel: Channel, current_user: User) -> None:
    if not channel.matrix_room_id:
        return
    repair_room_membership(channel.matrix_room_id, channel.server.owner, current_user)


def _notify_bot_replies(
    replies,
    *,
    channel: Channel,
    recipients: set[int],
) -> None:
    for reply in replies:
        if reply.event_id and reply.matrix_user_id:
            notify_channel_message(
                channel.id,
                channel.server_id,
                recipients,
                schemas.MessageRead(
                    event_id=reply.event_id,
                    sender=reply.matrix_user_id,
                    content=reply.content,
                    origin_server_ts=None,
                    is_bot=True,
                ).model_dump(),
            )


@router.post("", response_model=schemas.MessageRead, status_code=201)
def send_message(
    channel_id: int,
    payload: schemas.MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)

    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    recipients = {sm.user_id for sm in channel.server.members}
    recipients.add(channel.server.owner_id)
    bot_event = MessageEvent(
        channel=channel,
        sender_id=current_user.id,
        sender_username=current_user.username,
        content=payload.content,
    )

    # Gizli hamleler Matrix'e hiç yazılmaz. Böylece rakip, ilk oyuncunun komutunu gateway,
    # history veya kısa süreli bir UI yarışı üzerinden dahi göremez.
    if is_private_message_event(db, bot_event):
        replies = handle_message_event(db, bot_event)
        _notify_bot_replies(replies, channel=channel, recipients=recipients)
        return schemas.MessageRead(
            event_id=f"hidden-{payload.client_id or uuid.uuid4().hex}",
            sender=current_user.matrix_user_id or "",
            content="",
            origin_server_ts=None,
            client_id=payload.client_id,
            hidden=True,
        )

    try:
        event_id = matrix_client.send_message(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            payload.content,
            txn_id=payload.client_id,
        )
    except MatrixError as exc:
        if not is_not_in_room_error(exc):
            raise HTTPException(
                status_code=502,
                detail="Mesaj servisi geçici olarak kullanılamıyor; lütfen tekrar deneyin",
            ) from exc
        try:
            _repair_membership(channel, current_user)
            event_id = matrix_client.send_message(
                current_user.matrix_access_token,
                channel.matrix_room_id,
                payload.content,
                txn_id=payload.client_id,
            )
        except MatrixError as retry_exc:
            raise HTTPException(
                status_code=502,
                detail="Mesaj kanalı üyeliği otomatik onarılamadı; lütfen sayfayı yenileyip tekrar deneyin",
            ) from retry_exc

    message = schemas.MessageRead(
        event_id=event_id,
        sender=current_user.matrix_user_id,
        content=payload.content,
        origin_server_ts=None,
        client_id=payload.client_id,
    )

    # Kullanıcı mesajını bot işlemlerini bekletmeden tüm istemcilere aktar. İstemci doğrudan
    # bu payload'ı listeye ekler; yeniden 50 mesaj indirmesi gerekmez.
    notify_channel_message(
        channel_id,
        channel.server_id,
        recipients,
        message.model_dump(),
    )

    # Bot Engine: mesaj bir komutsa (ör. "/sunucu-durumu"), sunucuya eklenmiş botlar
    # ilgili plugin'i çalıştırıp cevabı kendi Matrix hesabıyla aynı odaya yazar.
    replies = handle_message_event(db, bot_event)

    # Senkron bot cevaplarının event_id'si biliniyorsa onları da doğrudan gateway'den gönder.
    _notify_bot_replies(replies, channel=channel, recipients=recipients)

    return message


@router.delete("/{event_id}", status_code=204)
def delete_message(
    channel_id: int,
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bir mesajı siler (Matrix redact). Yetkilendirmeyi Matrix uygular: kullanıcı yalnızca
    kendi mesajını (veya yeterli power level'a sahipse başkasının mesajını) silebilir."""
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)

    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    try:
        matrix_client.redact_message(current_user.matrix_access_token, channel.matrix_room_id, event_id)
    except MatrixError as exc:
        # Matrix yetki (power level) reddi büyük olasılıkla 403 içerir; kullanıcıya net dönelim.
        if "403" in str(exc):
            raise HTTPException(status_code=403, detail="Bu mesajı silme yetkiniz yok") from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    recipients = {sm.user_id for sm in channel.server.members}
    recipients.add(channel.server.owner_id)
    notify_channel_message(
        channel_id,
        channel.server_id,
        recipients,
        deleted_event_id=event_id,
    )


@router.patch("/{event_id}", response_model=schemas.MessageRead)
def edit_message(
    channel_id: int,
    event_id: str,
    payload: schemas.MessageEdit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)
    if not current_user.matrix_access_token or not current_user.matrix_user_id:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")
    try:
        original = matrix_client.get_event(
            current_user.matrix_access_token, channel.matrix_room_id, event_id
        )
        if original.get("sender") != current_user.matrix_user_id:
            raise HTTPException(status_code=403, detail="Yalnızca kendi mesajınızı düzenleyebilirsiniz")
        matrix_client.edit_message(
            current_user.matrix_access_token, channel.matrix_room_id, event_id, payload.content
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
    recipients = {sm.user_id for sm in channel.server.members}
    recipients.add(channel.server.owner_id)
    notify_channel_message(channel_id, channel.server_id, recipients, message.model_dump())
    return message


@router.get("", response_model=schemas.MessagePage)
def list_messages(
    channel_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)

    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    try:
        page = matrix_client.get_message_page(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            limit=limit,
            cursor=cursor,
        )
    except MatrixError as exc:
        if not is_not_in_room_error(exc):
            raise HTTPException(
                status_code=502,
                detail="Mesaj geçmişi geçici olarak yüklenemiyor; lütfen tekrar deneyin",
            ) from exc
        try:
            _repair_membership(channel, current_user)
            page = matrix_client.get_message_page(
                current_user.matrix_access_token,
                channel.matrix_room_id,
                limit=limit,
                cursor=cursor,
            )
        except MatrixError as retry_exc:
            raise HTTPException(
                status_code=502,
                detail="Mesaj kanalı üyeliği otomatik onarılamadı; lütfen sayfayı yenileyip tekrar deneyin",
            ) from retry_exc

    bot_matrix_ids = {
        link.bot.matrix_user_id
        for link in db.query(BotServerLink).filter(
            BotServerLink.server_id == channel.server_id
        )
        if link.bot.matrix_user_id
    }
    for message in page["items"]:
        message["is_bot"] = message.get("sender") in bot_matrix_ids
    return page
