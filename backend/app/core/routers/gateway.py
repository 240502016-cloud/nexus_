"""Kullanıcı başına kalıcı gateway WebSocket'i.

Sesli kanal soketi yalnızca kanaldayken vardır; oysa "birini kanala çağırma" (zil) için
kullanıcı hiçbir kanalda değilken bile ona ulaşmak gerekir. Bu gateway her oturum açan
kullanıcı için açık kalır ve iki şey sağlar:

- Presence: aynı sunucuları paylaşan üyelerin çevrimiçi/çevrimdışı durumu.
- Çağrı sinyali: call-invite / call-accept / call-reject / call-cancel olaylarını hedef
  kullanıcıya iletir. Çağrılar bellekte tutulur, DB'ye yazılmaz.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.auth import decode_user_id
from app.core.event_loop import get_main_loop
from app.core.models import Channel, ChannelType, Friendship, Server, ServerMember, User
from app.core.routers.voice import set_voice_state_listener, voice_manager
from app.database import SessionLocal


class GatewayManager:
    """Bellekte tutulan, kullanıcı başına (çok cihaz destekli) gateway bağlantıları."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        # user_id -> {"status": online|idle|dnd|invisible, "custom": str}
        self._status: dict[int, dict] = {}

    def is_online(self, user_id: int) -> bool:
        return user_id in self._connections

    def set_status(self, user_id: int, status: str, custom: str) -> None:
        self._status[user_id] = {"status": status, "custom": custom}

    def clear_status(self, user_id: int) -> None:
        self._status.pop(user_id, None)

    def presence_payload(self, user_id: int, username: str | None = None) -> dict:
        """Bir kullanıcının dışarıya gösterilecek presence'ı. 'invisible' seçilmişse çevrimdışı görünür."""
        connected = self.is_online(user_id)
        st = self._status.get(user_id, {"status": "online", "custom": ""})
        invisible = st["status"] == "invisible"
        shown_offline = invisible or not connected
        return {
            "type": "presence",
            "user_id": user_id,
            "username": username,
            "online": connected and not invisible,
            "status": "offline" if shown_offline else st["status"],
            "custom": "" if shown_offline else st["custom"],
        }

    def add(self, user_id: int, ws: WebSocket) -> bool:
        """Bağlantıyı kaydeder. Kullanıcı bu bağlantıyla çevrimiçi OLDUYSA True döner."""
        conns = self._connections.setdefault(user_id, set())
        was_offline = len(conns) == 0
        conns.add(ws)
        return was_offline

    def remove(self, user_id: int, ws: WebSocket) -> bool:
        """Bağlantıyı siler. Kullanıcı tümüyle çevrimdışı OLDUYSA True döner."""
        conns = self._connections.get(user_id)
        if not conns:
            return False
        conns.discard(ws)
        if not conns:
            self._connections.pop(user_id, None)
            return True
        return False

    async def send_to_user(self, user_id: int, message: dict) -> None:
        failed: list[WebSocket] = []
        for ws in list(self._connections.get(user_id, set())):
            try:
                await ws.send_json(message)
            except Exception:
                failed.append(ws)
        # Bazı ağ kopmalarında disconnect olayı geç gelebilir. Bozuk soketleri burada da
        # temizleyerek kullanıcının yanlış biçimde çevrimiçi görünmesini engelle.
        for ws in failed:
            self.remove(user_id, ws)


gateway_manager = GatewayManager()

VALID_STATUSES = {"online", "idle", "dnd", "invisible"}


async def _push_voice_state(channel_id: int, participants: list[dict], recipient_ids: set[int]) -> None:
    """voice.py'dan gelen roster değişimini yetkili (sunucu üyesi) kullanıcılara ilet.

    Böylece kanala GİRMEYEN üyeler de ses kanalındaki katılımcıları gerçek zamanlı görür.
    """
    message = {"type": "voice-channel-state", "channel_id": channel_id, "participants": participants}
    for uid in recipient_ids:
        await gateway_manager.send_to_user(uid, message)


set_voice_state_listener(_push_voice_state)


async def _broadcast_channel_message(
    channel_id: int,
    server_id: int,
    recipient_ids: set[int],
    message_payload: dict | None = None,
    deleted_event_id: str | None = None,
) -> None:
    message = {"type": "channel-message", "channel_id": channel_id, "server_id": server_id}
    if message_payload is not None:
        message["message"] = message_payload
    if deleted_event_id is not None:
        message["deleted_event_id"] = deleted_event_id
    for uid in recipient_ids:
        await gateway_manager.send_to_user(uid, message)


def notify_channel_message(
    channel_id: int,
    server_id: int,
    recipient_ids: set[int],
    message_payload: dict | None = None,
    deleted_event_id: str | None = None,
) -> None:
    """Senkron endpoint'ten (mesaj gönderme) çağrılır: kanaldaki yeni mesaj sinyalini gerçek
    zamanlı olarak üyelere iletmek üzere ana event loop'a planlar. Böylece istemciler 4 sn
    polling beklemeden mesajı anında görür (polling yine yedek olarak kalır)."""
    try:
        loop = get_main_loop()
    except RuntimeError:
        return
    asyncio.run_coroutine_threadsafe(
        _broadcast_channel_message(
            channel_id,
            server_id,
            set(recipient_ids),
            message_payload,
            deleted_event_id,
        ),
        loop,
    )


async def _broadcast_channel_meta(
    channel_id: int,
    server_id: int,
    recipient_ids: set[int],
    *,
    event_id: str | None = None,
    reactions: list[dict] | None = None,
    pins_changed: bool = False,
) -> None:
    payload: dict = {
        "type": "channel-message-meta",
        "channel_id": channel_id,
        "server_id": server_id,
        "pins_changed": pins_changed,
    }
    if event_id is not None:
        payload["event_id"] = event_id
    if reactions is not None:
        payload["reactions"] = reactions
    for uid in recipient_ids:
        await gateway_manager.send_to_user(uid, payload)


def notify_channel_meta(
    channel_id: int,
    server_id: int,
    recipient_ids: set[int],
    *,
    event_id: str | None = None,
    reactions: list[dict] | None = None,
    pins_changed: bool = False,
) -> None:
    try:
        loop = get_main_loop()
    except RuntimeError:
        return
    asyncio.run_coroutine_threadsafe(
        _broadcast_channel_meta(
            channel_id,
            server_id,
            set(recipient_ids),
            event_id=event_id,
            reactions=reactions,
            pins_changed=pins_changed,
        ),
        loop,
    )


async def _push_direct_message(
    conversation_id: int,
    recipient_ids: set[int],
    sender_id: int,
    message_payload: dict,
) -> None:
    payload = {
        "type": "direct-message",
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "message": message_payload,
    }
    for uid in recipient_ids:
        await gateway_manager.send_to_user(uid, payload)


def notify_direct_message(
    conversation_id: int,
    recipient_ids: set[int],
    sender_id: int,
    message_payload: dict,
) -> None:
    try:
        loop = get_main_loop()
    except RuntimeError:
        return
    asyncio.run_coroutine_threadsafe(
        _push_direct_message(conversation_id, set(recipient_ids), sender_id, message_payload),
        loop,
    )


def notify_social_event(user_id: int, event: str) -> None:
    try:
        loop = get_main_loop()
    except RuntimeError:
        return
    asyncio.run_coroutine_threadsafe(
        gateway_manager.send_to_user(user_id, {"type": "social-event", "event": event}),
        loop,
    )


router = APIRouter(tags=["gateway"])


def _co_member_ids(db: Session, user_id: int) -> set[int]:
    """Kullanıcının en az bir sunucuyu paylaştığı diğer kullanıcıların id kümesi."""
    member_server_ids = {
        sm.server_id for sm in db.query(ServerMember).filter(ServerMember.user_id == user_id).all()
    }
    owned_ids = {s.id for s in db.query(Server).filter(Server.owner_id == user_id).all()}
    server_ids = member_server_ids | owned_ids
    ids: set[int] = set()
    if server_ids:
        for sm in db.query(ServerMember).filter(ServerMember.server_id.in_(server_ids)).all():
            ids.add(sm.user_id)
        for s in db.query(Server).filter(Server.id.in_(server_ids)).all():
            ids.add(s.owner_id)
    friendships = (
        db.query(Friendship)
        .filter(
            Friendship.status == "accepted",
            (
                (Friendship.user_low_id == user_id)
                | (Friendship.user_high_id == user_id)
            ),
        )
        .all()
    )
    for friendship in friendships:
        ids.add(
            friendship.user_high_id
            if friendship.user_low_id == user_id
            else friendship.user_low_id
        )
    ids.discard(user_id)
    return ids


def _validate_invite(db: Session, caller_id: int, target_id: int, channel_id: int) -> Channel | None:
    """Arayan ve hedef aynı sunucunun üyesi mi ve kanal geçerli bir ses kanalı mı?"""
    channel = db.get(Channel, channel_id)
    if not channel or channel.type != ChannelType.VOICE:
        return None
    server = channel.server
    member_ids = {sm.user_id for sm in server.members}
    member_ids.add(server.owner_id)
    if caller_id in member_ids and target_id in member_ids:
        return channel
    return None


def _typing_recipients(
    db: Session,
    user_id: int,
    channel_id: int,
) -> tuple[Channel, set[int]] | None:
    channel = db.get(Channel, channel_id)
    if not channel or channel.type != ChannelType.TEXT:
        return None
    member_ids = {membership.user_id for membership in channel.server.members}
    member_ids.add(channel.server.owner_id)
    if user_id not in member_ids:
        return None
    member_ids.discard(user_id)
    return channel, member_ids


@router.websocket("/gateway")
async def gateway_socket(websocket: WebSocket, token: str = Query(...)):
    db = SessionLocal()
    try:
        user_id = decode_user_id(token)
        user = db.get(User, user_id) if user_id is not None else None
        if not user:
            await websocket.close(code=4401)
            return
        username = user.username
        co_members = _co_member_ids(db, user_id)
    finally:
        db.close()

    await websocket.accept()
    became_online = gateway_manager.add(user_id, websocket)

    # Bu kullanıcıya, paylaştığı üyelerden şu an çevrimiçi olanların presence'ını (durum dahil) bildir.
    presences = [
        gateway_manager.presence_payload(uid) for uid in co_members if gateway_manager.is_online(uid)
    ]
    await websocket.send_json({"type": "presence-init", "presences": presences, "self_id": user_id})
    # WebSocket olayı bağlantı kesikken kaçmış olsa bile istemci bu sinyalle kalıcı sosyal
    # durumu API'den yeniden uzlaştırır.
    await websocket.send_json({"type": "social-sync"})

    # Başlangıç snapshot'ı: kullanıcının görmeye yetkili olduğu ses kanallarındaki mevcut roster.
    # (Sayfa yenilendiğinde doğru mevcut durumun backend'den alınmasını sağlar.)
    for cid in voice_manager.rooms_for_recipient(user_id):
        await websocket.send_json(
            {"type": "voice-channel-state", "channel_id": cid, "participants": voice_manager.roster(cid)}
        )

    # İlk kez çevrimiçi olduysa ortak üyelere haber ver.
    if became_online:
        for uid in co_members:
            await gateway_manager.send_to_user(uid, gateway_manager.presence_payload(user_id, username))

    try:
        last_typing_forward: dict[int, float] = {}
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")
            target = data.get("to_user_id")
            channel_id = data.get("channel_id")

            if msg_type == "call-invite":
                if not isinstance(target, int) or not isinstance(channel_id, int):
                    continue
                db = SessionLocal()
                try:
                    channel = _validate_invite(db, user_id, target, channel_id)
                finally:
                    db.close()
                if channel is None:
                    await websocket.send_json({"type": "call-error", "reason": "invalid-target"})
                    continue
                if not gateway_manager.is_online(target):
                    await websocket.send_json(
                        {"type": "call-unavailable", "to_user_id": target, "channel_id": channel_id}
                    )
                    continue
                await gateway_manager.send_to_user(
                    target,
                    {
                        "type": "incoming-call",
                        "from_user": user_id,
                        "from_username": username,
                        "channel_id": channel_id,
                        "channel_name": channel.name,
                        "server_id": channel.server_id,
                    },
                )
            elif msg_type == "typing":
                typing = data.get("typing")
                if not isinstance(channel_id, int) or not isinstance(typing, bool):
                    continue
                now = time.monotonic()
                if typing and now - last_typing_forward.get(channel_id, 0.0) < 0.75:
                    continue
                last_typing_forward[channel_id] = now
                db = SessionLocal()
                try:
                    typing_target = _typing_recipients(db, user_id, channel_id)
                finally:
                    db.close()
                if typing_target is None:
                    continue
                channel, recipients = typing_target
                payload = {
                    "type": "channel-typing",
                    "channel_id": channel.id,
                    "server_id": channel.server_id,
                    "user_id": user_id,
                    "username": username,
                    "typing": typing,
                }
                for recipient_id in recipients:
                    await gateway_manager.send_to_user(recipient_id, payload)
            elif msg_type == "ping":
                # Uygulama katmanı heartbeat'i Cloudflare/NAT üzerindeki yarı-açık
                # bağlantıları hızlıca fark eder ve istemcinin yeniden bağlanmasını sağlar.
                await websocket.send_json({"type": "pong"})
            elif msg_type == "set-status":
                status = data.get("status")
                if status in VALID_STATUSES:
                    custom = str(data.get("custom") or "")[:128]
                    gateway_manager.set_status(user_id, status, custom)
                    payload = gateway_manager.presence_payload(user_id, username)
                    for uid in co_members:
                        await gateway_manager.send_to_user(uid, payload)
                    # Kendi UI'sının da güncellenmesi için gerçek (görünmez dahil) durumu geri gönder.
                    await websocket.send_json(
                        {"type": "self-status", "status": status, "custom": custom}
                    )
            elif msg_type in ("call-accept", "call-reject", "call-cancel"):
                if not isinstance(target, int):
                    continue
                forwarded = {
                    "call-accept": "call-accepted",
                    "call-reject": "call-rejected",
                    "call-cancel": "call-cancelled",
                }[msg_type]
                await gateway_manager.send_to_user(
                    target,
                    {"type": forwarded, "from_user": user_id, "channel_id": channel_id},
                )
    except WebSocketDisconnect:
        pass
    finally:
        went_offline = gateway_manager.remove(user_id, websocket)
        if went_offline:
            gateway_manager.clear_status(user_id)
            for uid in co_members:
                await gateway_manager.send_to_user(
                    uid,
                    {
                        "type": "presence",
                        "user_id": user_id,
                        "username": username,
                        "online": False,
                        "status": "offline",
                        "custom": "",
                    },
                )
