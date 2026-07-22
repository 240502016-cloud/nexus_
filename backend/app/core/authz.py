from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.models import Server, ServerMember, User


def ensure_server_member(db: Session, server: Server, user: User) -> None:
    if server.owner_id == user.id:
        return
    membership = db.get(ServerMember, {"user_id": user.id, "server_id": server.id})
    if not membership:
        raise HTTPException(status_code=403, detail="Bu sunucunun üyesi değilsiniz")


def ensure_server_owner(server: Server, user: User) -> None:
    if server.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Bu işlem için sunucu sahibi olmanız gerekir")
