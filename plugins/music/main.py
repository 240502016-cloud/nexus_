from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

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


def handle_command(context) -> str:
    """plugin.json'daki tüm 'muzik-*' komutları bu tek fonksiyona yönlendirilir;
    hangi komutun çalıştığı context.command'dan okunur (bkz. plugins/README.md)."""
    if context.server_id is None or context.bot_id is None:
        return "Bu komut sadece bir sunucu kanalından, bot üzerinden çalıştırılabilir."

    command = context.command
    args = (context.args or "").strip()

    if command == "muzik-listele":
        tracks = voice_session.list_tracks()
        if not tracks:
            return "Kütüphanede (plugins/music/library/) hiç ses dosyası yok."
        return "Kütüphanedeki parçalar: " + ", ".join(tracks)

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

    if command == "muzik-kuyruk":
        return session.status_text()

    if command == "muzik-sonraki":
        return _run(session.skip())

    return f"Bilinmeyen müzik komutu: {command}"
