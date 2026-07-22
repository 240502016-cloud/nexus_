"""Bot'un gerçekten sesli kanala katılıp ses akıttığı WebRTC mantığı.

Bot, platformun kendi sesli kanal signaling'ine (backend/app/core/routers/voice.py'deki
`voice_manager`) gerçek bir WebSocket açmadan doğrudan Python fonksiyon çağrısıyla katılır -
plugin'ler zaten backend süreciyle aynı yorumlayıcıda çalışıyor (bkz. moderation plugin'i).
`BotVoiceClient`, `voice_manager`'ın beklediği "ws" arayüzünü (sadece async `send_json`)
taklit ederek sinyal mesajlarını ağa göndermek yerine doğrudan bu modüle yönlendirir.

Bot'un "kullanıcı id"si olarak `-bot_id` kullanılır: gerçek kullanıcı id'leri hep pozitif
olduğundan, `voice_manager`'ın `dict[int, ...]` katılımcı tablosunda asla çakışmaz - bu
yüzden botun ayrı bir User/JWT hesabına ihtiyacı yok.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import av
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.sdp import candidate_from_sdp

from app.core.routers.voice import voice_manager

logger = logging.getLogger(__name__)

LIBRARY_DIR = Path(__file__).resolve().parent / "library"


def list_tracks() -> list[str]:
    if not LIBRARY_DIR.exists():
        return []
    return sorted(path.stem for path in LIBRARY_DIR.iterdir() if path.is_file())


def find_track(name: str) -> Path | None:
    """Kütüphane klasöründe dosya adına (uzantısız, büyük/küçük harf duyarsız) göre eşleşen ilk dosya."""
    name_lower = name.strip().lower()
    for stem in list_tracks():
        if stem.lower() == name_lower:
            matches = [p for p in LIBRARY_DIR.iterdir() if p.is_file() and p.stem.lower() == name_lower]
            return matches[0] if matches else None
    return None


def _track_duration_seconds(path: Path) -> float:
    container = av.open(str(path))
    try:
        return float(container.duration) / av.time_base
    finally:
        container.close()


class BotVoiceClient:
    """`voice_manager`'ın 'ws' parametresi için duck-typed sahte istemci."""

    def __init__(self, session: "MusicSession") -> None:
        self._session = session

    async def send_json(self, message: dict) -> None:
        await self._session.handle_signal(message)


class MusicSession:
    def __init__(self, server_id: int, channel_id: int, bot_id: int, bot_name: str) -> None:
        self.server_id = server_id
        self.channel_id = channel_id
        self.virtual_id = -bot_id
        self.bot_name = bot_name

        self.queue: list[Path] = []
        self.current: Path | None = None

        self._peers: dict[int, RTCPeerConnection] = {}
        self._relay = MediaRelay()
        self._player: MediaPlayer | None = None
        self._advance_task: asyncio.Task | None = None
        self._client = BotVoiceClient(self)

    # ---- Bağlantı yaşam döngüsü ----

    async def join(self) -> None:
        existing_peers = await voice_manager.join(self.channel_id, self.virtual_id, self.bot_name, self._client)
        await voice_manager.broadcast(
            self.channel_id,
            {"type": "peer-joined", "user_id": self.virtual_id, "username": self.bot_name, "muted": False},
            exclude_user_id=self.virtual_id,
        )
        for peer in existing_peers:
            await self._offer_to(peer["user_id"])

    async def leave(self) -> None:
        if self._advance_task:
            self._advance_task.cancel()
            self._advance_task = None
        for pc in list(self._peers.values()):
            await pc.close()
        self._peers.clear()
        self._player = None
        voice_manager.leave(self.channel_id, self.virtual_id)
        await voice_manager.broadcast(self.channel_id, {"type": "peer-left", "user_id": self.virtual_id})

    # ---- Sinyalleşme (voice.py'deki WebSocket handler ile birebir aynı sözleşme) ----

    async def handle_signal(self, message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "offer":
            await self._answer(message["from"], message["sdp"])
        elif msg_type == "answer":
            pc = self._peers.get(message["from"])
            if pc:
                await pc.setRemoteDescription(RTCSessionDescription(sdp=message["sdp"], type="answer"))
        elif msg_type == "ice-candidate":
            pc = self._peers.get(message["from"])
            candidate_data = message.get("candidate")
            if pc and candidate_data and candidate_data.get("candidate"):
                candidate = candidate_from_sdp(candidate_data["candidate"])
                candidate.sdpMid = candidate_data.get("sdpMid")
                candidate.sdpMLineIndex = candidate_data.get("sdpMLineIndex")
                await pc.addIceCandidate(candidate)
        # peer-joined/peer-left/mute-changed/speaking-changed: bot için aksiyon gerekmiyor -
        # yeni gerçek bir katılımcı zaten kendi tarafında bota offer gönderecek (mesh kuralı).

    async def _new_peer_connection(self, peer_id: int) -> RTCPeerConnection:
        pc = RTCPeerConnection()
        self._peers[peer_id] = pc
        # Track olmasa bile transceiver'ı baştan ekliyoruz - böylece şarkı sonra başlasa/değişse
        # bile yeniden negotiation gerekmeden sender.replaceTrack() ile akış başlatılabilir.
        transceiver = pc.addTransceiver("audio", direction="sendonly")
        if self._player is not None:
            transceiver.sender.replaceTrack(self._relay.subscribe(self._player.audio))
        return pc

    async def _offer_to(self, peer_id: int) -> None:
        pc = await self._new_peer_connection(peer_id)
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await self._wait_ice_complete(pc)
        await voice_manager.send_to(
            self.channel_id, peer_id, {"type": "offer", "from": self.virtual_id, "sdp": pc.localDescription.sdp}
        )

    async def _answer(self, peer_id: int, sdp: str) -> None:
        pc = await self._new_peer_connection(peer_id)
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await self._wait_ice_complete(pc)
        await voice_manager.send_to(
            self.channel_id, peer_id, {"type": "answer", "from": self.virtual_id, "sdp": pc.localDescription.sdp}
        )

    async def _wait_ice_complete(self, pc: RTCPeerConnection, timeout: float = 5.0) -> None:
        if pc.iceGatheringState == "complete":
            return
        done = asyncio.get_running_loop().create_future()

        @pc.on("icegatheringstatechange")
        def _on_change() -> None:
            if pc.iceGatheringState == "complete" and not done.done():
                done.set_result(None)

        try:
            await asyncio.wait_for(done, timeout=timeout)
        except asyncio.TimeoutError:
            pass  # elimizdeki SDP ile devam - bazı ICE adayları eksik kalabilir ama bağlantı genelde kurulur

    # ---- Kuyruk / oynatma ----

    async def enqueue(self, path: Path) -> str:
        self.queue.append(path)
        if self.current is None:
            return await self._advance()
        return f"'{path.stem}' kuyruğa eklendi (sırada {len(self.queue)}. parça)."

    async def skip(self) -> str:
        if self.current is None and not self.queue:
            return "Çalan veya kuyrukta bekleyen bir parça yok."
        return await self._advance()

    async def _advance(self) -> str:
        if self._advance_task is not None:
            self._advance_task.cancel()
            self._advance_task = None

        if not self.queue:
            self.current = None
            self._player = None
            self._switch_all_tracks(None)
            return "Kuyrukta başka parça yok."

        self.current = self.queue.pop(0)
        self._player = MediaPlayer(str(self.current))
        self._switch_all_tracks(self._relay.subscribe(self._player.audio))

        duration = _track_duration_seconds(self.current)
        self._advance_task = asyncio.ensure_future(self._auto_advance_after(duration))
        return f"Şimdi çalıyor: {self.current.stem}"

    async def _auto_advance_after(self, duration_seconds: float) -> None:
        try:
            await asyncio.sleep(duration_seconds)
            await self._advance()
        except asyncio.CancelledError:
            pass

    def _switch_all_tracks(self, track) -> None:
        for pc in self._peers.values():
            for sender in pc.getSenders():
                sender.replaceTrack(track)

    def status_text(self) -> str:
        lines = [f"Şimdi çalıyor: {self.current.stem}" if self.current else "Şu an bir şey çalmıyor."]
        lines.append("Kuyruk: " + ", ".join(p.stem for p in self.queue) if self.queue else "Kuyruk boş.")
        return "\n".join(lines)


_sessions: dict[int, MusicSession] = {}  # server_id -> MusicSession


def get_session(server_id: int) -> MusicSession | None:
    return _sessions.get(server_id)


def create_session(server_id: int, channel_id: int, bot_id: int, bot_name: str) -> MusicSession:
    session = MusicSession(server_id, channel_id, bot_id, bot_name)
    _sessions[server_id] = session
    return session


def remove_session(server_id: int) -> None:
    _sessions.pop(server_id, None)
