from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_owner
from app.core.matrix_client import MatrixError
from app.core.matrix_rooms import invite_and_join
from app.core.models import Role, Server, ServerJoinCode, ServerMember, User, utcnow
from app.core.rate_limit import RateLimiter
from app.core.routers.gateway import notify_social_event
from app.database import get_db

router = APIRouter(prefix="/server-join", tags=["server-join"])

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_join_limiter = RateLimiter(max_calls=12, window_seconds=60)


def _read(record: ServerJoinCode) -> schemas.ServerJoinCodeRead:
    return schemas.ServerJoinCodeRead(code=record.code, created_at=record.created_at)


def _server_for_owner(db: Session, server_id: int, current_user: User) -> Server:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)
    return server


def _new_code(db: Session) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(16))
        if not db.query(ServerJoinCode).filter(ServerJoinCode.code == code).first():
            return code
    raise HTTPException(status_code=503, detail="Davet kodu üretilemedi; lütfen tekrar deneyin")


@router.get("/servers/{server_id}/code", response_model=schemas.ServerJoinCodeRead)
def get_join_code(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _server_for_owner(db, server_id, current_user)
    record = db.get(ServerJoinCode, server_id)
    if not record:
        raise HTTPException(status_code=404, detail="Bu sunucu için paylaşım kodu oluşturulmamış")
    return _read(record)


@router.post("/servers/{server_id}/code", response_model=schemas.ServerJoinCodeRead)
def create_join_code(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _server_for_owner(db, server_id, current_user)
    record = db.get(ServerJoinCode, server_id)
    if record:
        return _read(record)
    record = ServerJoinCode(
        server_id=server_id,
        code=_new_code(db),
        created_by_id=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _read(record)


@router.put("/servers/{server_id}/code", response_model=schemas.ServerJoinCodeRead)
def rotate_join_code(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _server_for_owner(db, server_id, current_user)
    record = db.get(ServerJoinCode, server_id)
    if not record:
        record = ServerJoinCode(server_id=server_id, created_by_id=current_user.id, code="")
    record.code = _new_code(db)
    record.created_by_id = current_user.id
    record.created_at = utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return _read(record)


@router.delete("/servers/{server_id}/code", status_code=204)
def revoke_join_code(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _server_for_owner(db, server_id, current_user)
    record = db.get(ServerJoinCode, server_id)
    if record:
        db.delete(record)
        db.commit()


def _sync_text_rooms_best_effort(server: Server, member: User) -> None:
    """Ses üyeliğini Matrix arızasına bağlamadan mevcut metin odalarını hazırlamayı dener."""
    for channel in server.channels:
        if not channel.matrix_room_id:
            continue
        try:
            invite_and_join(channel.matrix_room_id, server.owner, member)
        except MatrixError:
            # Mesaj endpoint'i eksik üyeliği ayrıca onarabilir. Matrix'in geçici arızası
            # kullanıcının sunucuya ve ses kanallarına katılmasını engellememelidir.
            continue


@router.post("", response_model=schemas.ServerRead)
def join_server(
    payload: schemas.ServerJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not _join_limiter.allow(f"user:{current_user.id}"):
        raise HTTPException(status_code=429, detail="Çok fazla kod denemesi; bir dakika sonra tekrar deneyin")

    code = payload.code.strip().upper()
    record = db.query(ServerJoinCode).filter(ServerJoinCode.code == code).first()
    if not record:
        raise HTTPException(status_code=404, detail="Davet kodu geçersiz veya iptal edilmiş")

    server = record.server
    existing = db.get(ServerMember, {"user_id": current_user.id, "server_id": server.id})
    if existing:
        return server

    db.add(ServerMember(user_id=current_user.id, server_id=server.id))
    default_role = db.query(Role).filter(Role.server_id == server.id, Role.is_default.is_(True)).first()
    if default_role and default_role not in current_user.roles:
        current_user.roles.append(default_role)
    db.commit()
    db.refresh(server)

    # Üyelik önce kalıcılaştırılır: Matrix geçici olarak kapalı olsa bile kullanıcı ses kanalına girebilir.
    _sync_text_rooms_best_effort(server, current_user)
    notify_social_event(server.owner_id, "server-member-joined")
    notify_social_event(current_user.id, "server-membership-changed")
    return server
