from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.models import Server, ServerMember, User
from app.core.permissions import Permission


def ensure_server_member(db: Session, server: Server, user: User) -> None:
    if server.owner_id == user.id:
        return
    membership = db.get(ServerMember, {"user_id": user.id, "server_id": server.id})
    if not membership:
        raise HTTPException(status_code=403, detail="Bu sunucunun üyesi değilsiniz")


def ensure_server_owner(server: Server, user: User) -> None:
    if server.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Bu işlem için sunucu sahibi olmanız gerekir")


def has_server_permission(server: Server, user: User, permission: Permission) -> bool:
    if server.owner_id == user.id:
        return True
    return any(
        role.server_id == server.id and role.has_permission(permission)
        for role in user.roles
    )


def ensure_server_permission(server: Server, user: User, permission: Permission) -> None:
    if not has_server_permission(server, user, permission):
        raise HTTPException(status_code=403, detail="Bu işlem için yeterli yetkiniz yok")
