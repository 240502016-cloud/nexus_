from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member, ensure_server_owner
from app.core.models import Friendship, Server, ServerInvite, ServerMember, User, utcnow
from app.core.routers.gateway import notify_social_event
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


def _public(user: User) -> schemas.PublicUserRead:
    return schemas.PublicUserRead.model_validate(user)


def _invite_read(invite: ServerInvite, current_user_id: int) -> schemas.ServerInviteRead:
    return schemas.ServerInviteRead(
        id=invite.id,
        server_id=invite.server_id,
        server_name=invite.server.name,
        server_icon_url=invite.server.icon_url,
        inviter=_public(invite.inviter),
        invitee=_public(invite.invitee),
        direction="outgoing" if invite.inviter_id == current_user_id else "incoming",
        status=invite.status,
        created_at=invite.created_at,
        updated_at=invite.updated_at,
    )


@router.post("", response_model=schemas.ServerInviteRead, status_code=201)
def add_member(
    server_id: int,
    payload: schemas.MemberInvite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = _get_server(db, server_id)
    ensure_server_owner(server, current_user)

    user = db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    low_id, high_id = sorted((current_user.id, user.id))
    friendship = (
        db.query(Friendship)
        .filter(
            Friendship.user_low_id == low_id,
            Friendship.user_high_id == high_id,
            Friendship.status == "accepted",
        )
        .first()
    )
    if not friendship:
        raise HTTPException(status_code=403, detail="Sunucuya yalnızca arkadaşlar davet edilebilir")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Kendinize sunucu daveti gönderemezsiniz")
    if not user.matrix_access_token:
        raise HTTPException(status_code=409, detail="Kullanıcının Matrix hesabı yok")

    existing = db.get(ServerMember, {"user_id": user.id, "server_id": server.id})
    if existing:
        raise HTTPException(status_code=409, detail="Kullanıcı zaten bu sunucunun üyesi")

    invite = (
        db.query(ServerInvite)
        .filter(ServerInvite.server_id == server.id, ServerInvite.invitee_id == user.id)
        .first()
    )
    if invite and invite.status == "pending":
        raise HTTPException(status_code=409, detail="Bu kullanıcıya zaten bekleyen bir davet var")
    if invite:
        invite.inviter_id = current_user.id
        invite.status = "pending"
        invite.created_at = utcnow()
        invite.updated_at = utcnow()
    else:
        invite = ServerInvite(
            server_id=server.id,
            inviter_id=current_user.id,
            invitee_id=user.id,
            status="pending",
        )
        db.add(invite)

    db.commit()
    db.refresh(invite)
    notify_social_event(user.id, "server-invite")
    return _invite_read(invite, current_user.id)


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
