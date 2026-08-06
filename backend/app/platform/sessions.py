from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authz import ensure_server_member
from app.core.models import Channel, Server, User
from app.platform.events import append_event
from app.platform.models import (
    ExperienceSession,
    ExperienceSessionPlayer,
    ExperienceWsTicket,
    utcnow,
)


SUPPORTED_MODULES = {
    "ai_board_game",
    "ai_commentator",
    "ai_escape_room",
    "ai_roast_battle",
    "hidden_role_game",
    "highlight_generator",
    "meme_generator",
    "shared_story",
}


def _conflict(session: ExperienceSession) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"message": "Oturum revizyonu güncel değil", "current_revision": session.revision},
    )


def _check_revision(session: ExperienceSession, expected_revision: int) -> None:
    if session.revision != expected_revision:
        raise _conflict(session)


def _get_session(db: Session, session_id: str, *, lock: bool = False) -> ExperienceSession:
    query = db.query(ExperienceSession).filter(ExperienceSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = query.first()
    if not session:
        raise HTTPException(status_code=404, detail="Deneyim oturumu bulunamadı")
    return session


def ensure_session_access(db: Session, session: ExperienceSession, user: User) -> None:
    server = db.get(Server, session.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, user)


def ensure_session_player(db: Session, session: ExperienceSession, user_id: int) -> ExperienceSessionPlayer:
    player = db.get(ExperienceSessionPlayer, {"session_id": session.id, "user_id": user_id})
    if not player:
        raise HTTPException(status_code=403, detail="Bu deneyim oturumunun oyuncusu değilsiniz")
    return player


def create_session(
    db: Session,
    *,
    server_id: int,
    module_type: str,
    owner: User,
    idempotency_key: str,
    channel_id: int | None = None,
    settings: dict | None = None,
) -> ExperienceSession:
    if module_type not in SUPPORTED_MODULES:
        raise HTTPException(status_code=422, detail="Desteklenmeyen deneyim modülü")
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, owner)
    if channel_id is not None:
        channel = db.get(Channel, channel_id)
        if not channel or channel.server_id != server_id:
            raise HTTPException(status_code=422, detail="Kanal bu sunucuya ait değil")

    existing = (
        db.query(ExperienceSession)
        .filter(
            ExperienceSession.owner_id == owner.id,
            ExperienceSession.module_type == module_type,
            ExperienceSession.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return existing

    session = ExperienceSession(
        module_type=module_type,
        server_id=server_id,
        channel_id=channel_id,
        owner_id=owner.id,
        idempotency_key=idempotency_key,
        settings=settings or {},
    )
    db.add(session)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(ExperienceSession)
            .filter(
                ExperienceSession.owner_id == owner.id,
                ExperienceSession.module_type == module_type,
                ExperienceSession.idempotency_key == idempotency_key,
            )
            .first()
        )
        if concurrent:
            return concurrent
        raise
    db.add(ExperienceSessionPlayer(session_id=session.id, user_id=owner.id, seat=0))
    append_event(
        db,
        session,
        "session.created",
        {"module_type": module_type, "owner_id": owner.id, "max_players": session.max_players},
        idempotency_key=f"create:{idempotency_key}",
    )
    db.commit()
    return _get_session(db, session.id)


def ai_seats(session: ExperienceSession) -> list[int]:
    """AI'ın oynadığı koltuk numaraları. Boş liste = tamamı insan oturumu.

    AI koltukları ``experience_session_players`` tablosunda **satır tutmaz**: o tablonun
    ``user_id`` sütunu ``users.id``'ye FK'dir ve modül tablolarının hepsi aynı şekilde
    gerçek kullanıcıya bağlıdır. Sahte bir sistem kullanıcısı açmak yerine AI koltukları
    yalnız burada, oturum ayarlarında tutulur; modüller kendi JSON/şifreli durumlarında
    ``ai:<koltuk>`` anahtarıyla temsil eder.
    """
    return [int(seat) for seat in (session.settings or {}).get("ai_seats", [])]


def participant_key(user_id: int | None, seat: int) -> str:
    """Modül JSON durumlarında katılımcı anahtarı: insan için id, AI için ``ai:<koltuk>``."""
    return str(user_id) if user_id is not None else f"ai:{seat}"


def create_active_session(
    db: Session,
    *,
    server_id: int,
    module_type: str,
    owner: User,
    player_ids: list[int],
    idempotency_key: str,
    channel_id: int | None = None,
    settings: dict | None = None,
    ai_seat_count: int = 0,
    min_seats: int = 3,
    max_seats: int = 3,
    min_human_players: int = 2,
) -> ExperienceSession:
    """Atomically create an already assembled module session.

    ``player_ids`` yalnız gerçek kullanıcılardır. ``ai_seat_count`` kadar koltuk AI'a
    ayrılır ve toplam koltuk sayısı ``[min_seats, max_seats]`` aralığında olmalıdır.
    Varsayılanlar (3/3, AI yok) eski davranışı korur — ``ai_roast_battle`` bunu kullanır.
    """
    if module_type not in SUPPORTED_MODULES:
        raise HTTPException(status_code=422, detail="Desteklenmeyen deneyim modülü")
    if ai_seat_count < 0:
        raise HTTPException(status_code=422, detail="AI koltuk sayısı negatif olamaz")
    if len(player_ids) != len(set(player_ids)):
        raise HTTPException(status_code=422, detail="Aynı oyuncu birden çok koltuğa oturamaz")
    if len(player_ids) < min_human_players:
        raise HTTPException(
            status_code=422, detail=f"Oturum en az {min_human_players} gerçek oyuncu gerektirir"
        )
    total_seats = len(player_ids) + ai_seat_count
    if not min_seats <= total_seats <= max_seats:
        detail = (
            f"Bu modül {min_seats} koltuk gerektirir"
            if min_seats == max_seats
            else f"Bu modül {min_seats}-{max_seats} koltukla oynanır"
        )
        raise HTTPException(status_code=422, detail=detail)
    if owner.id not in player_ids:
        raise HTTPException(status_code=422, detail="Oturum sahibi oyuncular arasında olmalı")

    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, owner)
    players = {user.id: user for user in db.query(User).filter(User.id.in_(player_ids)).all()}
    if set(players) != set(player_ids):
        raise HTTPException(status_code=422, detail="Oyunculardan biri bulunamadı")
    for player in players.values():
        ensure_server_member(db, server, player)
    if channel_id is not None:
        channel = db.get(Channel, channel_id)
        if not channel or channel.server_id != server_id:
            raise HTTPException(status_code=422, detail="Kanal bu sunucuya ait değil")

    existing = (
        db.query(ExperienceSession)
        .filter(
            ExperienceSession.owner_id == owner.id,
            ExperienceSession.module_type == module_type,
            ExperienceSession.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return existing

    seat_settings = dict(settings or {})
    seat_settings["ai_seats"] = list(range(len(player_ids), total_seats))
    session = ExperienceSession(
        module_type=module_type,
        server_id=server_id,
        channel_id=channel_id,
        owner_id=owner.id,
        idempotency_key=idempotency_key,
        settings=seat_settings,
        max_players=total_seats,
    )
    db.add(session)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(ExperienceSession)
            .filter(
                ExperienceSession.owner_id == owner.id,
                ExperienceSession.module_type == module_type,
                ExperienceSession.idempotency_key == idempotency_key,
            )
            .first()
        )
        if concurrent:
            return concurrent
        raise

    ordered_ids = [owner.id, *sorted(user_id for user_id in player_ids if user_id != owner.id)]
    for seat, user_id in enumerate(ordered_ids):
        db.add(
            ExperienceSessionPlayer(
                session_id=session.id,
                user_id=user_id,
                seat=seat,
                ready=True,
            )
        )
    append_event(
        db,
        session,
        "session.created",
        {"module_type": module_type, "owner_id": owner.id, "max_players": total_seats},
        idempotency_key=f"create:{idempotency_key}",
    )
    session.status = "active"
    session.started_at = utcnow()
    session.revision = 1
    append_event(
        db,
        session,
        "session.started",
        {"player_ids": ordered_ids, "ai_seats": seat_settings["ai_seats"]},
        idempotency_key="session:start",
    )
    db.commit()
    return _get_session(db, session.id)


def join_session(
    db: Session, session_id: str, user: User, expected_revision: int
) -> ExperienceSession:
    session = _get_session(db, session_id, lock=True)
    ensure_session_access(db, session, user)
    existing = db.get(ExperienceSessionPlayer, {"session_id": session.id, "user_id": user.id})
    if existing:
        return session
    _check_revision(session, expected_revision)
    if session.status != "lobby":
        raise HTTPException(status_code=409, detail="Başlamış oturuma yeni oyuncu katılamaz")
    occupied = {player.seat for player in session.players}
    seat = next((candidate for candidate in range(session.max_players) if candidate not in occupied), None)
    if seat is None:
        raise HTTPException(status_code=409, detail="Oturum dolu")
    session.revision += 1
    db.add(ExperienceSessionPlayer(session_id=session.id, user_id=user.id, seat=seat))
    append_event(
        db,
        session,
        "session.player_joined",
        {"user_id": user.id, "seat": seat},
        idempotency_key=f"join:{user.id}",
    )
    db.commit()
    return _get_session(db, session.id)


def set_ready(
    db: Session, session_id: str, user: User, expected_revision: int, ready: bool
) -> ExperienceSession:
    session = _get_session(db, session_id, lock=True)
    ensure_session_access(db, session, user)
    player = ensure_session_player(db, session, user.id)
    if player.ready == ready:
        return session
    _check_revision(session, expected_revision)
    if session.status != "lobby":
        raise HTTPException(status_code=409, detail="Hazır durumu yalnız lobby içinde değiştirilebilir")
    player.ready = ready
    session.revision += 1
    append_event(
        db,
        session,
        "session.player_ready_changed",
        {"user_id": user.id, "ready": ready},
        idempotency_key=f"ready:{user.id}:{session.revision}",
    )
    db.commit()
    return _get_session(db, session.id)


def start_session(
    db: Session, session_id: str, user: User, expected_revision: int
) -> ExperienceSession:
    session = _get_session(db, session_id, lock=True)
    ensure_session_access(db, session, user)
    ensure_session_player(db, session, user.id)
    if session.status == "active":
        return session
    _check_revision(session, expected_revision)
    if session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Oturumu yalnız sahibi başlatabilir")
    if session.status != "lobby":
        raise HTTPException(status_code=409, detail="Oturum başlatılabilir durumda değil")
    if len(session.players) != session.max_players or not all(player.ready for player in session.players):
        raise HTTPException(status_code=409, detail="Başlatmak için tüm koltuklar dolu ve hazır olmalı")
    session.status = "active"
    session.started_at = utcnow()
    session.revision += 1
    append_event(
        db,
        session,
        "session.started",
        {"player_ids": [player.user_id for player in session.players]},
        idempotency_key="session:start",
    )
    db.commit()
    return _get_session(db, session.id)


def session_to_dict(session: ExperienceSession) -> dict:
    return {
        "id": session.id,
        "module_type": session.module_type,
        "server_id": session.server_id,
        "channel_id": session.channel_id,
        "owner_id": session.owner_id,
        "status": session.status,
        "revision": session.revision,
        "max_players": session.max_players,
        "settings_version": session.settings_version,
        "settings": session.settings,
        "players": [
            {
                "user_id": player.user_id,
                "username": player.user.username,
                "display_name": player.user.display_name,
                "seat": player.seat,
                "ready": player.ready,
                "joined_at": player.joined_at,
            }
            for player in session.players
        ],
        "created_at": session.created_at,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "updated_at": session.updated_at,
    }


def issue_ws_ticket(
    db: Session, session: ExperienceSession, user: User, *, ttl_seconds: int = 60
) -> tuple[str, datetime]:
    ensure_session_access(db, session, user)
    ensure_session_player(db, session, user.id)
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires_at = utcnow() + timedelta(seconds=max(10, min(ttl_seconds, 300)))
    db.add(
        ExperienceWsTicket(
            token_hash=token_hash,
            session_id=session.id,
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    db.commit()
    return raw, expires_at


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def consume_ws_ticket(db: Session, session_id: str, raw_ticket: str) -> int | None:
    token_hash = hashlib.sha256(raw_ticket.encode("utf-8")).hexdigest()
    ticket = (
        db.query(ExperienceWsTicket)
        .filter(ExperienceWsTicket.token_hash == token_hash)
        .with_for_update()
        .first()
    )
    if (
        not ticket
        or ticket.session_id != session_id
        or ticket.used_at is not None
        or _aware(ticket.expires_at) < utcnow()
    ):
        return None
    ticket.used_at = utcnow()
    db.commit()
    return ticket.user_id
