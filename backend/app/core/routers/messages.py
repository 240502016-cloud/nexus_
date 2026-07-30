import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.bot_engine.dispatcher import MessageEvent, handle_message_event, is_private_message_event
from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member, ensure_server_permission, has_server_permission
from app.core.matrix_client import MatrixError, matrix_client
from app.core.matrix_rooms import is_not_in_room_error, repair_room_membership
from app.core.models import BotServerLink, Channel, ChannelType, User
from app.core.permissions import Permission
from app.core.routers.gateway import notify_channel_message, notify_channel_meta
from app.database import get_db

router = APIRouter(prefix="/channels/{channel_id}/messages", tags=["messages"])
_MENTION_PATTERN = re.compile(r"(?<![\w@])@([A-Za-z0-9_.-]{2,32})")


def _recipient_ids(channel: Channel) -> set[int]:
    recipients = {membership.user_id for membership in channel.server.members}
    recipients.add(channel.server.owner_id)
    return recipients


def _mentioned_users(channel: Channel, content: str) -> list[User]:
    names = {match.casefold() for match in _MENTION_PATTERN.findall(content)}
    if not names:
        return []
    users = [membership.user for membership in channel.server.members]
    if all(user.id != channel.server.owner_id for user in users):
        users.append(channel.server.owner)
    return [
        user
        for user in users
        if user.username.casefold() in names and user.matrix_user_id
    ]


def _reaction_summary(events: list[dict], current_matrix_user_id: str) -> list[dict]:
    grouped: dict[str, dict] = {}
    for event in events:
        emoji = event.get("content", {}).get("m.relates_to", {}).get("key")
        if not isinstance(emoji, str):
            continue
        item = grouped.setdefault(emoji, {"emoji": emoji, "count": 0, "me": False})
        item["count"] += 1
        if event.get("sender") == current_matrix_user_id:
            item["me"] = True
    return [grouped[key] for key in sorted(grouped)]


def _message_from_event(event: dict) -> schemas.MessageRead:
    content = event.get("content", {})
    if event.get("type") != "m.room.message" or not isinstance(content.get("body"), str):
        raise HTTPException(status_code=422, detail="Bu Matrix olayı bir mesaj değil")
    return schemas.MessageRead(
        event_id=str(event.get("event_id", "")),
        sender=str(event.get("sender", "")),
        content=content["body"],
        origin_server_ts=event.get("origin_server_ts"),
    )


def _reply_preview(
    access_token: str,
    room_id: str,
    event_id: str | None,
) -> schemas.MessageReplyPreview | None:
    if not event_id:
        return None
    try:
        event = matrix_client.get_event(access_token, room_id, event_id)
    except MatrixError as exc:
        raise HTTPException(status_code=404, detail="Yanıtlanan mesaj bulunamadı") from exc
    content = event.get("content", {})
    if event.get("type") != "m.room.message" or not isinstance(content.get("body"), str):
        raise HTTPException(status_code=422, detail="Bu içeriğe yanıt verilemiyor")
    return schemas.MessageReplyPreview(
        event_id=event_id,
        sender=str(event.get("sender", "")),
        content=content["body"][:500],
    )


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
    reply_to = _reply_preview(
        current_user.matrix_access_token,
        channel.matrix_room_id,
        payload.reply_to_event_id,
    )

    recipients = _recipient_ids(channel)
    mentioned_users = _mentioned_users(channel, payload.content)
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
            reply_to=reply_to.model_dump() if reply_to else None,
            mention_user_ids=[
                user.matrix_user_id for user in mentioned_users if user.matrix_user_id
            ],
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
                reply_to=reply_to.model_dump() if reply_to else None,
                mention_user_ids=[
                    user.matrix_user_id for user in mentioned_users if user.matrix_user_id
                ],
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
        reply_to=reply_to,
        mentioned_user_ids=[user.id for user in mentioned_users],
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

    recipients = _recipient_ids(channel)
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
    mentioned_users = _mentioned_users(channel, payload.content)
    try:
        original = matrix_client.get_event(
            current_user.matrix_access_token, channel.matrix_room_id, event_id
        )
        if original.get("sender") != current_user.matrix_user_id:
            raise HTTPException(status_code=403, detail="Yalnızca kendi mesajınızı düzenleyebilirsiniz")
        matrix_client.edit_message(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            event_id,
            payload.content,
            mention_user_ids=[
                user.matrix_user_id for user in mentioned_users if user.matrix_user_id
            ],
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
        mentioned_user_ids=[user.id for user in mentioned_users],
    )
    recipients = _recipient_ids(channel)
    notify_channel_message(channel_id, channel.server_id, recipients, message.model_dump())
    return message


@router.put("/{event_id}/reactions", response_model=schemas.MessageReactionUpdate)
def toggle_reaction(
    channel_id: int,
    event_id: str,
    payload: schemas.MessageReactionToggle,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)
    if not current_user.matrix_access_token or not current_user.matrix_user_id:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")
    emoji = payload.emoji.strip()
    if not emoji or len(emoji) > 16 or any(character.isspace() for character in emoji):
        raise HTTPException(status_code=422, detail="Geçersiz reaksiyon")
    try:
        original = matrix_client.get_event(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            event_id,
        )
        if original.get("type") != "m.room.message":
            raise HTTPException(status_code=422, detail="Yalnızca mesajlara reaksiyon verilebilir")
        reactions = matrix_client.get_reactions(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            event_id,
        )
        own = [
            event
            for event in reactions
            if event.get("sender") == current_user.matrix_user_id
            and event.get("content", {}).get("m.relates_to", {}).get("key") == emoji
        ]
        if own:
            for reaction in own:
                reaction_event_id = reaction.get("event_id")
                if isinstance(reaction_event_id, str):
                    matrix_client.redact_message(
                        current_user.matrix_access_token,
                        channel.matrix_room_id,
                        reaction_event_id,
                    )
        else:
            matrix_client.send_reaction(
                current_user.matrix_access_token,
                channel.matrix_room_id,
                event_id,
                emoji,
            )
        reactions = matrix_client.get_reactions(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            event_id,
        )
    except HTTPException:
        raise
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail="Reaksiyon güncellenemedi") from exc

    summary = _reaction_summary(reactions, current_user.matrix_user_id)
    notify_channel_meta(
        channel.id,
        channel.server_id,
        _recipient_ids(channel),
        event_id=event_id,
        reactions=summary,
    )
    return schemas.MessageReactionUpdate(event_id=event_id, reactions=summary)


@router.get("/search", response_model=list[schemas.MessageRead])
def search_messages(
    channel_id: int,
    q: str = Query(min_length=2, max_length=200),
    user_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=30, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)
    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")
    sender: str | None = None
    if user_id is not None:
        member_ids = _recipient_ids(channel)
        if user_id not in member_ids:
            raise HTTPException(status_code=404, detail="Kullanıcı bu sunucuda değil")
        target = db.get(User, user_id)
        sender = target.matrix_user_id if target else None
        if not sender:
            return []
    try:
        events = matrix_client.search_messages(
            current_user.matrix_access_token,
            channel.matrix_room_id,
            q.strip(),
            sender=sender,
            limit=limit,
        )
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail="Mesaj araması geçici olarak kullanılamıyor") from exc
    messages: list[schemas.MessageRead] = []
    for event in events:
        try:
            messages.append(_message_from_event(event))
        except HTTPException:
            continue
    return messages


@router.get("/pins", response_model=schemas.PinnedMessagesRead)
def list_pinned_messages(
    channel_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)
    if not current_user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")
    try:
        event_ids = matrix_client.get_pinned_event_ids(
            current_user.matrix_access_token,
            channel.matrix_room_id,
        )
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail="Sabit mesajlar alınamadı") from exc
    items: list[schemas.MessageRead] = []
    for event_id in event_ids[-50:]:
        try:
            event = matrix_client.get_event(
                current_user.matrix_access_token,
                channel.matrix_room_id,
                event_id,
            )
            items.append(_message_from_event(event))
        except (MatrixError, HTTPException):
            # Silinmiş veya erişilemeyen eski bir pin bütün paneli kullanılamaz yapmamalı.
            continue
    return schemas.PinnedMessagesRead(
        items=items,
        can_manage=has_server_permission(channel.server, current_user, Permission.MANAGE_MESSAGES),
    )


def _set_message_pinned(
    channel: Channel,
    current_user: User,
    event_id: str,
    pinned: bool,
) -> None:
    ensure_server_permission(channel.server, current_user, Permission.MANAGE_MESSAGES)
    owner_token = channel.server.owner.matrix_access_token
    if not owner_token:
        raise HTTPException(status_code=409, detail="Sunucu sahibinin Matrix hesabı yok")
    try:
        event = matrix_client.get_event(owner_token, channel.matrix_room_id, event_id)
        if event.get("type") != "m.room.message":
            raise HTTPException(status_code=422, detail="Yalnızca mesajlar sabitlenebilir")
        event_ids = matrix_client.get_pinned_event_ids(owner_token, channel.matrix_room_id)
        if pinned and event_id not in event_ids:
            event_ids.append(event_id)
        if not pinned:
            event_ids = [item for item in event_ids if item != event_id]
        matrix_client.set_pinned_event_ids(owner_token, channel.matrix_room_id, event_ids[-50:])
    except HTTPException:
        raise
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail="Sabit mesajlar güncellenemedi") from exc
    notify_channel_meta(
        channel.id,
        channel.server_id,
        _recipient_ids(channel),
        event_id=event_id,
        pins_changed=True,
    )


@router.put("/{event_id}/pin", status_code=204)
def pin_message(
    channel_id: int,
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)
    _set_message_pinned(channel, current_user, event_id, True)


@router.delete("/{event_id}/pin", status_code=204)
def unpin_message(
    channel_id: int,
    event_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    channel = _get_text_channel(db, channel_id)
    ensure_server_member(db, channel.server, current_user)
    _set_message_pinned(channel, current_user, event_id, False)


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
            current_matrix_user_id=current_user.matrix_user_id,
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
                current_matrix_user_id=current_user.matrix_user_id,
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
    matrix_ids = {
        matrix_id
        for message in page["items"]
        for matrix_id in message.get("mention_user_ids", [])
        if isinstance(matrix_id, str)
    }
    mentioned_id_map = {
        user.matrix_user_id: user.id
        for user in db.query(User).filter(User.matrix_user_id.in_(matrix_ids)).all()
        if user.matrix_user_id
    } if matrix_ids else {}
    for message in page["items"]:
        raw_mentions = message.pop("mention_user_ids", [])
        message["mentioned_user_ids"] = [
            mentioned_id_map[matrix_id]
            for matrix_id in raw_mentions
            if matrix_id in mentioned_id_map
        ]
    return page
