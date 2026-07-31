from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.core.event_loop import get_main_loop
from app.core.models import Channel, ChannelType
from app.database import SessionLocal

# Plugin loader, main.py'yi importlib.util.spec_from_file_location ile paket bağlamı olmadan
# yüklüyor (bkz. backend/app/plugins_engine/loader.py::_load_module) - bu yüzden burada da
# `from . import voice_session` gibi göreli import çalışmaz; aynı dosya-yolu tabanlı yöntemle
# kendimiz yüklüyoruz.
_voice_session_spec = importlib.util.spec_from_file_location(
    "nexus_plugin_music_voice_session", Path(__file__).parent / "voice_session.py"
)
voice_session = importlib.util.module_from_spec(_voice_session_spec)
_voice_session_spec.loader.exec_module(voice_session)

YOUTUBE_EVENT_PREFIX = "NEXUS_YOUTUBE_EVENT:"
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeSession:
    def __init__(
        self,
        video_id: str,
        position_seconds: float,
        playing: bool,
        updated_at_ms: int,
    ) -> None:
        self.video_id = video_id
        self.position_seconds = position_seconds
        self.playing = playing
        self.updated_at_ms = updated_at_ms


_youtube_sessions: dict[int, YouTubeSession] = {}  # text channel id -> synchronized player state


def _run(coro, timeout: float = 10.0):
    """Senkron plugin thread'inden ana asyncio event loop'a iş verip sonucu bekler."""
    future = asyncio.run_coroutine_threadsafe(coro, get_main_loop())
    return future.result(timeout=timeout)


def _find_voice_channel(server_id: int, name: str) -> Channel | None:
    db = SessionLocal()
    try:
        return (
            db.query(Channel)
            .filter(Channel.server_id == server_id, Channel.type == ChannelType.VOICE, Channel.name == name)
            .first()
        )
    finally:
        db.close()


def _youtube_video_id(value: str) -> str | None:
    candidate = value.strip()
    if _YOUTUBE_ID_RE.fullmatch(candidate):
        return candidate
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    video_id = ""
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
            video_id = parsed.path.strip("/").split("/", 1)[1].split("/", 1)[0]
    return video_id if _YOUTUBE_ID_RE.fullmatch(video_id) else None


def _youtube_position(session: YouTubeSession, now_ms: int) -> float:
    if not session.playing:
        return session.position_seconds
    return session.position_seconds + max(0, now_ms - session.updated_at_ms) / 1000


def _youtube_event(session: YouTubeSession, body: str, *, stopped: bool = False) -> str:
    now_ms = int(time.time() * 1000)
    payload = {
        "type": "youtube_state",
        "video_id": session.video_id,
        "playing": session.playing and not stopped,
        "stopped": stopped,
        "position_seconds": round(_youtube_position(session, now_ms), 3),
        "issued_at_ms": now_ms,
    }
    return YOUTUBE_EVENT_PREFIX + json.dumps(payload, separators=(",", ":")) + "\n" + body


def handle_command(context) -> str:
    """plugin.json'daki tüm 'muzik-*' komutları bu tek fonksiyona yönlendirilir;
    hangi komutun çalıştığı context.command'dan okunur (bkz. plugins/README.md)."""
    if context.server_id is None or context.bot_id is None:
        return "Bu komut sadece bir sunucu kanalından, bot üzerinden çalıştırılabilir."

    command = context.command
    args = (context.args or "").strip()
    youtube_key = context.channel_id

    if command == "muzik-listele":
        tracks = voice_session.list_tracks()
        if not tracks:
            return "Kütüphanede (plugins/music/library/) hiç ses dosyası yok."
        return "Kütüphanedeki parçalar: " + ", ".join(tracks)

    if command == "youtube":
        video_id = _youtube_video_id(args)
        if video_id is None:
            return "Kullanım: /youtube <YouTube bağlantısı veya video kimliği>"
        now_ms = int(time.time() * 1000)
        youtube_session = YouTubeSession(video_id, 0, True, now_ms)
        _youtube_sessions[youtube_key] = youtube_session
        return _youtube_event(youtube_session, "YouTube izleme odası başlatıldı.")

    if command in {"youtube-duraklat", "youtube-devam", "youtube-durdur", "youtube-durum"}:
        youtube_session = _youtube_sessions.get(youtube_key)
        if youtube_session is None:
            return "Aktif bir YouTube izleme odası yok. Önce /youtube <bağlantı> kullanın."
        now_ms = int(time.time() * 1000)
        if command == "youtube-duraklat":
            youtube_session.position_seconds = _youtube_position(youtube_session, now_ms)
            youtube_session.playing = False
            youtube_session.updated_at_ms = now_ms
            return _youtube_event(youtube_session, "YouTube oynatımı herkes için duraklatıldı.")
        if command == "youtube-devam":
            youtube_session.position_seconds = _youtube_position(youtube_session, now_ms)
            youtube_session.playing = True
            youtube_session.updated_at_ms = now_ms
            return _youtube_event(youtube_session, "YouTube oynatımı herkes için devam ettirildi.")
        if command == "youtube-durdur":
            youtube_session.position_seconds = _youtube_position(youtube_session, now_ms)
            youtube_session.playing = False
            youtube_session.updated_at_ms = now_ms
            _youtube_sessions.pop(youtube_key, None)
            return _youtube_event(youtube_session, "YouTube izleme odası kapatıldı.", stopped=True)
        return _youtube_event(youtube_session, "YouTube izleme odasının güncel durumu paylaşıldı.")

    if command == "muzik-katil":
        if not args:
            return "Kullanım: /muzik-katil <sesli-kanal-adı>"
        if voice_session.get_session(context.server_id) is not None:
            return "Zaten bir sesli kanaldayım. Önce /muzik-ayril kullanın."
        channel = _find_voice_channel(context.server_id, args)
        if channel is None:
            return f"'{args}' adında sesli bir kanal bulunamadı."

        session = voice_session.create_session(
            context.server_id, channel.id, context.bot_id, context.bot_name or "music-bot"
        )
        try:
            _run(session.join())
        except Exception as exc:
            voice_session.remove_session(context.server_id)
            return f"Sesli kanala katılamadım: {exc}"
        return f"'{args}' sesli kanalına katıldım. /muzik-ekle <parça> ile şarkı ekleyebilirsiniz."

    session = voice_session.get_session(context.server_id)
    if session is None:
        return "Şu an bir sesli kanalda değilim. Önce /muzik-katil <sesli-kanal-adı> kullanın."

    if command == "muzik-ayril":
        _run(session.leave())
        voice_session.remove_session(context.server_id)
        return "Sesli kanaldan ayrıldım."

    if command == "muzik-ekle":
        if not args:
            return "Kullanım: /muzik-ekle <parça-adı> (bkz. /muzik-listele)"
        track = voice_session.find_track(args)
        if track is None:
            return f"'{args}' kütüphanede bulunamadı. /muzik-listele ile mevcut parçaları görebilirsiniz."
        return _run(session.enqueue(track))

    if command in {"muzik-url", "radyo"}:
        if not args:
            return f"Kullanım: /{command} <doğrudan ses veya internet radyo adresi>"
        try:
            remote_track = voice_session.resolve_remote_track(args)
        except ValueError as exc:
            return str(exc)
        return _run(session.enqueue(remote_track))

    if command == "muzik-kuyruk":
        return session.status_text()

    if command == "muzik-sonraki":
        return _run(session.skip())

    return f"Bilinmeyen müzik komutu: {command}"
