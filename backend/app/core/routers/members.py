from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member, ensure_server_owner
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Server, ServerMember, User
from app.database import get_db

router = APIRouter(prefix="/servers/{server_id}/members", tags=["members"])


def _get_server(db: Session, server_id: int) -> Server:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    return server


@router.get("", response_model=list[schemas.MemberRead])
def list_members(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _get_server(db, server_id)
    ensure_server_member(db, server, current_user)
    return [
        schemas.MemberRead(
            id=membership.user.id,
            username=membership.user.username,
            display_name=membership.user.display_name,
            avatar_url=membership.user.avatar_url,
            joined_at=membership.joined_at,
        )
        for membership in server.members
    ]


@router.post("", status_code=201)
def add_member(
    server_id: int,
    username: str = Query(..., description="Sunucuya davet edilecek kullanıcının kullanıcı adı"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _get_server(db, server_id)
    ensure_server_owner(server, current_user)

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    if not user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    existing = db.get(ServerMember, {"user_id": user.id, "server_id": server.id})
    if existing:
        raise HTTPException(status_code=409, detail="Kullanıcı zaten bu sunucunun üyesi")

    owner = server.owner
    for channel in server.channels:
        if not channel.matrix_room_id:
            continue
        try:
            matrix_client.invite_user(owner.matrix_access_token, channel.matrix_room_id, user.matrix_user_id)
            matrix_client.join_room(user.matrix_access_token, channel.matrix_room_id)
        except MatrixError as exc:
            raise HTTPException(status_code=502, detail=f"Kanala katılım başarısız: {exc}") from exc

    db.add(ServerMember(user_id=user.id, server_id=server.id))
    default_role = next((r for r in server.roles if r.is_default), None)
    if default_role:
        user.roles.append(default_role)

    db.commit()
    return {"status": "ok"}
