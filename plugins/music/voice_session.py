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
import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import av
import requests
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.sdp import candidate_from_sdp

from app.core.models import Server
from app.core.routers.voice import notify_voice_state, voice_manager
from app.database import SessionLocal

logger = logging.getLogger(__name__)

LIBRARY_DIR = Path(__file__).resolve().parent / "library"
_AUDIO_CONTENT_TYPES = {
    "application/octet-stream",
    "application/ogg",
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/aac",
    "audio/aacp",
    "audio/flac",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
    "audio/x-flac",
    "audio/x-mpegurl",
    "audio/x-wav",
}


class RemoteTrack:
    def __init__(self, url: str, label: str) -> None:
        self.url = url
        self.label = label


TrackSource = Path | RemoteTrack


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
        return float(container.duration or 0) / av.time_base
    finally:
        container.close()


def _validate_public_host(hostname: str, port: int) -> None:
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost" or normalized.endswith(".localhost") or normalized.endswith(".local"):
        raise ValueError("Yerel ağ adresleri müzik kaynağı olarak kullanılamaz.")
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Ses adresinin sunucu adı çözümlenemedi.") from exc
    if not addresses:
        raise ValueError("Ses adresi herhangi bir IP adresine çözümlenemedi.")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("Yerel, özel veya ayrılmış ağ adresleri müzik kaynağı olarak kullanılamaz.")


def resolve_remote_track(raw_url: str) -> RemoteTrack:
    """Genel internetteki doğrudan ses/radyo URL'sini SSRF'e karşı doğrula."""
    current = raw_url.strip()
    for _redirect in range(4):
        parsed = urlparse(current)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Yalnızca geçerli http:// veya https:// ses adresleri kullanılabilir.")
        if parsed.username or parsed.password:
            raise ValueError("Kullanıcı adı veya parola içeren ses adresleri kabul edilmez.")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("Ses adresindeki port geçerli değil.") from exc
        _validate_public_host(parsed.hostname, port)
        try:
            response = requests.get(
                current,
                allow_redirects=False,
                headers={"User-Agent": "NexusMusicBot/0.2"},
                stream=True,
                timeout=(4, 8),
            )
        except requests.RequestException as exc:
            raise ValueError("Ses adresine ulaşılamadı.") from exc
        try:
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Ses adresi geçersiz bir yönlendirme döndürdü.")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type not in _AUDIO_CONTENT_TYPES and not content_type.startswith("audio/"):
                raise ValueError(
                    "Adres doğrudan bir ses veya internet radyo akışı döndürmüyor. "
                    "YouTube bağlantıları için /youtube kullanın."
                )
            path_name = Path(unquote(parsed.path)).stem.strip()
            label = path_name or parsed.hostname
            return RemoteTrack(url=current, label=label[:120])
        except requests.HTTPError as exc:
            raise ValueError(f"Ses adresi HTTP {response.status_code} döndürdü.") from exc
        finally:
            response.close()
    raise ValueError("Ses adresi çok fazla yönlendirme yaptı.")


def _source_label(source: TrackSource) -> str:
    return source.stem if isinstance(source, Path) else source.label


def _source_location(source: TrackSource) -> str:
    return str(source) if isinstance(source, Path) else source.url


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

        self.queue: list[TrackSource] = []
        self.current: TrackSource | None = None

        self._peers: dict[int, RTCPeerConnection] = {}
        self._relay = MediaRelay()
        self._player: MediaPlayer | None = None
        self._advance_task: asyncio.Task | None = None
        self._client = BotVoiceClient(self)

    # ---- Bağlantı yaşam döngüsü ----

    async def join(self) -> None:
        db = SessionLocal()
        try:
            server = db.get(Server, self.server_id)
            if server is None:
                raise RuntimeError("Sunucu bulunamadı")
            recipients = {member.user_id for member in server.members}
            recipients.add(server.owner_id)
        finally:
            db.close()
        existing_peers = await voice_manager.join(
            self.channel_id,
            self.server_id,
            recipients,
            self.virtual_id,
            self.bot_name,
            None,
            self._client,
        )
        await voice_manager.broadcast(
            self.channel_id,
            {
                "type": "peer-joined",
                "user_id": self.virtual_id,
                "username": self.bot_name,
                "avatar_url": None,
                "muted": False,
                "deafened": False,
            },
            exclude_user_id=self.virtual_id,
        )
        await notify_voice_state(self.channel_id)
        # Mesh sözleşmesinde yeni katılan taraf offer üretir. Bot yeni katılımcı olduğundan,
        # kanalda zaten bulunan her gerçek kullanıcıya kendisi teklif göndermelidir.
        for peer in existing_peers:
            peer_id = peer.get("user_id")
            if isinstance(peer_id, int) and peer_id > 0:
                await self._offer_to(peer_id)

    async def leave(self) -> None:
        if self._advance_task:
            self._advance_task.cancel()
            self._advance_task = None
        for pc in list(self._peers.values()):
            await pc.close()
        self._peers.clear()
        self._player = None
        recipients = voice_manager.recipients(self.channel_id)
        voice_manager.leave(self.channel_id, self.virtual_id)
        await voice_manager.broadcast(self.channel_id, {"type": "peer-left", "user_id": self.virtual_id})
        await notify_voice_state(self.channel_id, recipients)

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

    async def enqueue(self, source: TrackSource) -> str:
        self.queue.append(source)
        if self.current is None:
            return await self._advance()
        return f"'{_source_label(source)}' kuyruğa eklendi (sırada {len(self.queue)}. parça)."

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
        self._player = MediaPlayer(_source_location(self.current))
        self._switch_all_tracks(self._relay.subscribe(self._player.audio))

        duration = _track_duration_seconds(self.current) if isinstance(self.current, Path) else 0
        if duration > 0:
            self._advance_task = asyncio.ensure_future(self._auto_advance_after(duration))
        return f"Şimdi çalıyor: {_source_label(self.current)}"

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
        lines = [
            f"Şimdi çalıyor: {_source_label(self.current)}"
            if self.current
            else "Şu an bir şey çalmıyor."
        ]
        lines.append(
            "Kuyruk: " + ", ".join(_source_label(source) for source in self.queue)
            if self.queue
            else "Kuyruk boş."
        )
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
