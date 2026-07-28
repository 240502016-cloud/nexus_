"""Sesli kanal WebRTC signaling'i.

Ses verisinin kendisi buradan geçmez - katılımcılar arasında doğrudan (mesh, WebRTC)
akar. Bu WebSocket sadece offer/answer/ICE candidate mesajlarını ilgili karşı tarafa
relay eder ve katılımcı listesi/mute durumu gibi oda durumunu yayınlar.

Yeni katılan taraf, kendisine gönderilen mevcut katılımcı listesindeki herkese "offer"
gönderir (mesh bağlantı kurma sorumluluğu her zaman yeni gelende); bu sayede aynı ikili
arasında çift bağlantı kurulmaz.

Ayrıca oda durumu (kimler kanalda, mute/deafen/speaking) her değişimde bir dinleyici
callback'i üzerinden gateway'e bildirilir; böylece kanala GİRMEYEN sunucu üyeleri de
katılımcıları gerçek zamanlı görebilir. voice -> gateway bağımlılığı callback ile kurulur
(doğrudan import edilmez), bu da döngüsel import'u önler.
"""

from __future__ import annotations

import json
import base64
import hashlib
import hmac
import ipaddress
import time
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from app.config import settings
from app.core.auth import decode_user_id, get_current_user
from app.core.models import Channel, ChannelType, ServerMember, User
from app.database import SessionLocal


class VoiceConnectionManager:
    """Bellekte tutulan sesli kanal katılımcıları ve WebSocket bağlantıları.

    Oda yapısı: channel_id -> {"server_id", "recipients": set[user_id], "users": {user_id: info}}
    recipients = o kanalın sunucusundaki tüm üyeler (roster'ı görmeye yetkili kişiler).
    """

    def __init__(self) -> None:
        self._rooms: dict[int, dict] = {}

    @staticmethod
    def _participant(uid: int, info: dict) -> dict:
        return {
            "user_id": uid,
            "username": info["username"],
            "avatar_url": info.get("avatar_url"),
            "muted": info["muted"],
            "deafened": info["deafened"],
            "speaking": info["speaking"],
        }

    async def join(
        self,
        channel_id: int,
        server_id: int,
        recipients: set[int],
        user_id: int,
        username: str,
        avatar_url: str | None,
        ws: WebSocket,
    ) -> list[dict]:
        room = self._rooms.setdefault(
            channel_id, {"server_id": server_id, "recipients": set(recipients), "users": {}}
        )
        # Üyelik değişmiş olabilir; her katılımda alıcı kümesini tazele.
        room["server_id"] = server_id
        room["recipients"] = set(recipients)
        users = room["users"]
        # Aynı hesap F5/reconnect ile yeni bir socket açtığında eski bağlantı kısa süre daha
        # yaşayabilir. Kullanıcıyı kendi peer listesine sokma; aksi halde tarayıcı kendisiyle
        # RTCPeerConnection kurmaya çalışıp "connection aborted" üretebilir.
        existing = [
            self._participant(uid, info)
            for uid, info in users.items()
            if uid != user_id
        ]
        users[user_id] = {
            "ws": ws,
            "username": username,
            "avatar_url": avatar_url,
            "muted": False,
            "deafened": False,
            "speaking": False,
        }
        return existing

    def leave(self, channel_id: int, user_id: int, ws: WebSocket | None = None) -> bool:
        """Aktif bağlantıyı kaldır.

        ``ws`` verildiğinde yalnızca halen odada kayıtlı socket aynıysa silinir. Böylece eski
        bir socket'in gecikmiş ``finally`` bloğu, onun yerini alan yeni bağlantıyı düşüremez.
        Bot gibi sanal katılımcılar ``ws`` vermeden önceki davranışı kullanmaya devam eder.
        """
        room = self._rooms.get(channel_id)
        if not room:
            return False
        info = room["users"].get(user_id)
        if info is None or (ws is not None and info.get("ws") is not ws):
            return False
        room["users"].pop(user_id, None)
        if not room["users"]:
            self._rooms.pop(channel_id, None)
        return True

    def _set(self, channel_id: int, user_id: int, key: str, value) -> None:
        room = self._rooms.get(channel_id)
        if room and user_id in room["users"]:
            room["users"][user_id][key] = value

    def set_muted(self, channel_id: int, user_id: int, muted: bool) -> None:
        self._set(channel_id, user_id, "muted", muted)

    def set_deafened(self, channel_id: int, user_id: int, deafened: bool) -> None:
        self._set(channel_id, user_id, "deafened", deafened)

    def set_speaking(self, channel_id: int, user_id: int, speaking: bool) -> None:
        self._set(channel_id, user_id, "speaking", speaking)

    def roster(self, channel_id: int) -> list[dict]:
        room = self._rooms.get(channel_id)
        if not room:
            return []
        return [self._participant(uid, info) for uid, info in room["users"].items()]

    def recipients(self, channel_id: int) -> set[int]:
        room = self._rooms.get(channel_id)
        return set(room["recipients"]) if room else set()

    def rooms_for_recipient(self, user_id: int) -> list[int]:
        return [cid for cid, room in self._rooms.items() if user_id in room["recipients"]]

    async def broadcast(self, channel_id: int, message: dict, exclude_user_id: int | None = None) -> None:
        room = self._rooms.get(channel_id)
        users = room["users"] if room else {}
        for uid, info in list(users.items()):
            if uid == exclude_user_id:
                continue
            try:
                await info["ws"].send_json(message)
            except Exception:
                pass  # bağlantı kopmuş olabilir; disconnect handler zaten temizleyecek

    async def send_to(self, channel_id: int, user_id: int, message: dict) -> None:
        room = self._rooms.get(channel_id)
        info = room["users"].get(user_id) if room else None
        if info:
            try:
                await info["ws"].send_json(message)
            except Exception:
                pass


voice_manager = VoiceConnectionManager()

# Oda durumu değişince çağrılan dinleyici (gateway tarafından register edilir).
# İmza: (channel_id, participants, recipient_ids) -> None
VoiceStateListener = Callable[[int, list[dict], set[int]], Awaitable[None]]
_voice_state_listener: Optional[VoiceStateListener] = None


def set_voice_state_listener(listener: VoiceStateListener) -> None:
    global _voice_state_listener
    _voice_state_listener = listener


async def _notify_voice_state(channel_id: int, recipients: set[int] | None = None) -> None:
    """Kanalın güncel roster'ını yetkili üyelere (gateway üzerinden) bildir."""
    if _voice_state_listener is None:
        return
    recips = recipients if recipients is not None else voice_manager.recipients(channel_id)
    participants = voice_manager.roster(channel_id)
    try:
        await _voice_state_listener(channel_id, participants, recips)
    except Exception:
        pass


async def notify_voice_state(channel_id: int, recipients: set[int] | None = None) -> None:
    """Yerleşik gerçek-zamanlı plugin'ler için güvenli roster yayın noktası."""
    await _notify_voice_state(channel_id, recipients)


router = APIRouter(tags=["voice"])


@router.get("/voice/ice-servers")
def voice_ice_servers(current_user: User = Depends(get_current_user)) -> dict:
    """Return free public STUN plus TURN only when its external address is Internet-routable."""
    expires_at = int(time.time()) + max(60, settings.turn_credential_ttl_seconds)
    ice_servers: list[dict] = [{"urls": "stun:stun.cloudflare.com:3478"}]

    # Hamachi/özel/CGNAT adresini dış istemcilere TURN diye vermek bağlantıyı saniyelerce
    # bekletir. Ücretsiz STUN ile doğrudan P2P denenir; yalnız gerçekten genel bir coturn
    # adresi yapılandırıldıysa relay kimlik bilgisi eklenir.
    external_address = (settings.turn_external_ip or settings.turn_domain).strip()
    turn_is_public = bool(settings.turn_domain and settings.turn_auth_secret and external_address)
    try:
        address = ipaddress.ip_address(external_address)
        hamachi_range = ipaddress.ip_network("25.0.0.0/8")
        cgnat_range = ipaddress.ip_network("100.64.0.0/10")
        turn_is_public = turn_is_public and not (
            address in hamachi_range
            or address in cgnat_range
            or address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_unspecified
            or address.is_reserved
        )
    except ValueError:
        # Alan adı kullanılmışsa yönlendirilebilir kabul edilir; yönetici coturn DNS kaydını
        # Cloudflare proxy'siz (DNS only) olarak yayınlamalıdır.
        pass

    if not turn_is_public:
        return {"ice_servers": ice_servers, "expires_at": expires_at}

    username = f"{expires_at}:{current_user.id}"
    digest = hmac.new(
        settings.turn_auth_secret.encode("utf-8"), username.encode("utf-8"), hashlib.sha1
    ).digest()
    credential = base64.b64encode(digest).decode("ascii")
    turn_host = settings.turn_domain
    turn_urls = [
        f"turn:{turn_host}:{settings.turn_port}?transport=udp",
        f"turn:{turn_host}:{settings.turn_port}?transport=tcp",
    ]
    ice_servers.extend(
        [
            {"urls": f"stun:{turn_host}:{settings.turn_port}"},
            {"urls": turn_urls, "username": username, "credential": credential},
        ]
    )
    return {"ice_servers": ice_servers, "expires_at": expires_at}


@router.websocket("/channels/{channel_id}/voice")
async def voice_socket(websocket: WebSocket, channel_id: int, token: str = Query(...)):
    db = SessionLocal()
    try:
        user_id = decode_user_id(token)
        user = db.get(User, user_id) if user_id is not None else None
        if not user:
            await websocket.close(code=4401)
            return

        channel = db.get(Channel, channel_id)
        if not channel or channel.type != ChannelType.VOICE:
            await websocket.close(code=4404)
            return

        is_owner = channel.server.owner_id == user.id
        membership = db.get(ServerMember, {"user_id": user.id, "server_id": channel.server_id})
        if not is_owner and not membership:
            await websocket.close(code=4403)
            return

        username = user.username
        avatar_url = user.avatar_url
        server_id = channel.server_id
        # Roster'ı görmeye yetkili kişiler: sunucunun tüm üyeleri + sahibi.
        recipients = {sm.user_id for sm in channel.server.members}
        recipients.add(channel.server.owner_id)
    finally:
        db.close()

    await websocket.accept()
    existing_peers = await voice_manager.join(
        channel_id, server_id, recipients, user_id, username, avatar_url, websocket
    )
    await websocket.send_json({"type": "peers", "peers": existing_peers, "self_id": user_id})
    await voice_manager.broadcast(
        channel_id,
        {
            "type": "peer-joined",
            "user_id": user_id,
            "username": username,
            "avatar_url": avatar_url,
            "muted": False,
            "deafened": False,
        },
        exclude_user_id=user_id,
    )
    await _notify_voice_state(channel_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")
            if msg_type in ("offer", "answer", "ice-candidate"):
                target = data.get("to")
                if isinstance(target, int):
                    payload = {k: v for k, v in data.items() if k != "to"}
                    payload["from"] = user_id
                    await voice_manager.send_to(channel_id, target, payload)
            elif msg_type == "mute":
                muted = bool(data.get("muted"))
                voice_manager.set_muted(channel_id, user_id, muted)
                await voice_manager.broadcast(
                    channel_id,
                    {"type": "mute-changed", "user_id": user_id, "muted": muted},
                    exclude_user_id=user_id,
                )
                await _notify_voice_state(channel_id)
            elif msg_type == "deafen":
                deafened = bool(data.get("deafened"))
                voice_manager.set_deafened(channel_id, user_id, deafened)
                await voice_manager.broadcast(
                    channel_id,
                    {"type": "deafen-changed", "user_id": user_id, "deafened": deafened},
                    exclude_user_id=user_id,
                )
                await _notify_voice_state(channel_id)
            elif msg_type == "speaking":
                speaking = bool(data.get("speaking"))
                voice_manager.set_speaking(channel_id, user_id, speaking)
                await voice_manager.broadcast(
                    channel_id,
                    {"type": "speaking-changed", "user_id": user_id, "speaking": speaking},
                    exclude_user_id=user_id,
                )
                await _notify_voice_state(channel_id)
    except WebSocketDisconnect:
        pass
    finally:
        # Oda silinmeden ÖNCE alıcıları yakala; ayrıldıktan sonra (belki boş) roster'ı onlara bildir.
        recipients_before = voice_manager.recipients(channel_id)
        removed = voice_manager.leave(channel_id, user_id, websocket)
        # Eski bir socket yeni bağlantıyla değiştirilmişse gecikmiş kapanış olayını yayınlama.
        if removed:
            await voice_manager.broadcast(channel_id, {"type": "peer-left", "user_id": user_id})
            await _notify_voice_state(channel_id, recipients_before)
