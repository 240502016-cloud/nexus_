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
    members = [
        schemas.MemberRead(
            id=membership.user.id,
            username=membership.user.username,
            display_name=membership.user.display_name,
            avatar_url=membership.user.avatar_url,
            joined_at=membership.joined_at,
        )
        for membership in server.members
    ]
    if all(member.id != server.owner_id for member in members):
        members.insert(
            0,
            schemas.MemberRead(
                id=server.owner.id,
                username=server.owner.username,
                display_name=server.owner.display_name,
                avatar_url=server.owner.avatar_url,
                joined_at=server.owner.created_at,
            ),
        )
    return members


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


@router.delete("/{user_id}", status_code=204)
def remove_member(
    server_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Üyeyi sunucudan çıkarır. Sahip herkesi çıkarabilir; bir üye kendini çıkarabilir (ayrıl).
    Sunucu sahibi çıkarılamaz (önce sahiplik devri gerekir)."""
    server = _get_server(db, server_id)
    if user_id == server.owner_id:
        raise HTTPException(status_code=400, detail="Sunucu sahibi çıkarılamaz")
    if current_user.id != server.owner_id and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok")

    membership = db.get(ServerMember, {"user_id": user_id, "server_id": server_id})
    if not membership:
        raise HTTPException(status_code=404, detail="Üye bulunamadı")

    # Kullanıcıdan bu sunucuya ait rolleri kaldır.
    server_role_ids = {role.id for role in server.roles}
    target = db.get(User, user_id)
    if target:
        target.roles = [role for role in target.roles if role.id not in server_role_ids]

    db.delete(membership)
    db.commit()
