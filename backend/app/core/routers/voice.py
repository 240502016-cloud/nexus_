"""Sesli kanal WebRTC signaling'i.

Ses verisinin kendisi buradan geçmez - katılımcılar arasında doğrudan (mesh, WebRTC)
akar. Bu WebSocket sadece offer/answer/ICE candidate mesajlarını ilgili karşı tarafa
relay eder ve katılımcı listesi/mute durumu gibi oda durumunu yayınlar.

Yeni katılan taraf, kendisine gönderilen mevcut katılımcı listesindeki herkese "offer"
gönderir (mesh bağlantı kurma sorumluluğu her zaman yeni gelende); bu sayede aynı ikili
arasında çift bağlantı kurulmaz.
"""

from __future__ import annotations

import json
import base64
import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from app.config import settings
from app.core.auth import decode_user_id, get_current_user
from app.core.models import Channel, ChannelType, ServerMember, User
from app.database import SessionLocal


class VoiceConnectionManager:
    """Bellekte tutulan sesli kanal katılımcıları ve WebSocket bağlantıları."""

    def __init__(self) -> None:
        self._channels: dict[int, dict[int, dict]] = {}

    async def join(self, channel_id: int, user_id: int, username: str, ws: WebSocket) -> list[dict]:
        room = self._channels.setdefault(channel_id, {})
        existing = [
            {"user_id": uid, "username": info["username"], "muted": info["muted"]} for uid, info in room.items()
        ]
        room[user_id] = {"ws": ws, "username": username, "muted": False}
        return existing

    def leave(self, channel_id: int, user_id: int) -> None:
        room = self._channels.get(channel_id)
        if room:
            room.pop(user_id, None)
            if not room:
                self._channels.pop(channel_id, None)

    def set_muted(self, channel_id: int, user_id: int, muted: bool) -> None:
        room = self._channels.get(channel_id)
        if room and user_id in room:
            room[user_id]["muted"] = muted

    async def broadcast(self, channel_id: int, message: dict, exclude_user_id: int | None = None) -> None:
        room = self._channels.get(channel_id, {})
        for uid, info in list(room.items()):
            if uid == exclude_user_id:
                continue
            try:
                await info["ws"].send_json(message)
            except Exception:
                pass  # bağlantı kopmuş olabilir; disconnect handler zaten temizleyecek

    async def send_to(self, channel_id: int, user_id: int, message: dict) -> None:
        room = self._channels.get(channel_id, {})
        info = room.get(user_id)
        if info:
            try:
                await info["ws"].send_json(message)
            except Exception:
                pass


voice_manager = VoiceConnectionManager()

router = APIRouter(tags=["voice"])


@router.get("/voice/ice-servers")
def voice_ice_servers(current_user: User = Depends(get_current_user)) -> dict:
    """Return short-lived TURN credentials; the shared coturn secret never reaches browsers."""
    if not settings.turn_domain or not settings.turn_auth_secret:
        raise HTTPException(status_code=503, detail="TURN sunucusu yapılandırılmamış")

    expires_at = int(time.time()) + max(60, settings.turn_credential_ttl_seconds)
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
    return {
        "ice_servers": [
            {"urls": f"stun:{turn_host}:{settings.turn_port}"},
            {"urls": turn_urls, "username": username, "credential": credential},
        ],
        "expires_at": expires_at,
    }


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
    finally:
        db.close()

    await websocket.accept()
    existing_peers = await voice_manager.join(channel_id, user_id, username, websocket)
    await websocket.send_json({"type": "peers", "peers": existing_peers})
    await voice_manager.broadcast(
        channel_id,
        {"type": "peer-joined", "user_id": user_id, "username": username, "muted": False},
        exclude_user_id=user_id,
    )

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
            elif msg_type == "speaking":
                await voice_manager.broadcast(
                    channel_id,
                    {"type": "speaking-changed", "user_id": user_id, "speaking": bool(data.get("speaking"))},
                    exclude_user_id=user_id,
                )
    except WebSocketDisconnect:
        pass
    finally:
        voice_manager.leave(channel_id, user_id)
        await voice_manager.broadcast(channel_id, {"type": "peer-left", "user_id": user_id})
