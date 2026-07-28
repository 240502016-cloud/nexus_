from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Friendship, ServerInvite, ServerMember, User
from app.core.routers.gateway import notify_social_event
from app.database import get_db

router = APIRouter(prefix="/server-invites", tags=["server-invites"])


def _public(user: User) -> schemas.PublicUserRead:
    return schemas.PublicUserRead.model_validate(user)


def _read(invite: ServerInvite, current_user_id: int) -> schemas.ServerInviteRead:
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


def _participating_invite(db: Session, invite_id: int, user_id: int) -> ServerInvite:
    invite = db.get(ServerInvite, invite_id)
    if not invite or user_id not in (invite.inviter_id, invite.invitee_id):
        raise HTTPException(status_code=404, detail="Sunucu daveti bulunamadı")
    return invite


def _friendship_is_accepted(db: Session, user_a: int, user_b: int) -> bool:
    low_id, high_id = sorted((user_a, user_b))
    return (
        db.query(Friendship)
        .filter(
            Friendship.user_low_id == low_id,
            Friendship.user_high_id == high_id,
            Friendship.status == "accepted",
        )
        .first()
        is not None
    )


def _already_joined(exc: MatrixError) -> bool:
    detail = str(exc).casefold()
    return "already joined" in detail or "already in the room" in detail


def _already_invited(exc: MatrixError) -> bool:
    detail = str(exc).casefold()
    return "already invited" in detail or "already been invited" in detail


@router.get("", response_model=schemas.ServerInviteList)
def list_server_invites(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invites = (
        db.query(ServerInvite)
        .filter(
            ServerInvite.status == "pending",
            or_(
                ServerInvite.inviter_id == current_user.id,
                ServerInvite.invitee_id == current_user.id,
            ),
        )
        .order_by(ServerInvite.created_at.desc())
        .all()
    )
    incoming = [_read(item, current_user.id) for item in invites if item.invitee_id == current_user.id]
    outgoing = [_read(item, current_user.id) for item in invites if item.inviter_id == current_user.id]
    return schemas.ServerInviteList(incoming=incoming, outgoing=outgoing)


@router.post("/{invite_id}/accept", response_model=schemas.ServerRead)
def accept_server_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invite = _participating_invite(db, invite_id, current_user.id)
    if invite.invitee_id != current_user.id:
        raise HTTPException(status_code=403, detail="Kendi gönderdiğiniz daveti kabul edemezsiniz")
    if invite.status != "pending":
        raise HTTPException(status_code=409, detail="Bu davet artık beklemiyor")
    if not _friendship_is_accepted(db, invite.inviter_id, current_user.id):
        raise HTTPException(status_code=409, detail="Davet sahibi artık arkadaş listenizde değil")

    server = invite.server
    existing = db.get(ServerMember, {"user_id": current_user.id, "server_id": server.id})
    if not existing:
        owner = server.owner
        if (
            not owner.matrix_access_token
            or not current_user.matrix_access_token
            or not current_user.matrix_user_id
        ):
            raise HTTPException(status_code=409, detail="Matrix hesabı eksik; davet kabul edilemedi")
        for channel in server.channels:
            if not channel.matrix_room_id:
                continue
            try:
                matrix_client.invite_user(
                    owner.matrix_access_token,
                    channel.matrix_room_id,
                    current_user.matrix_user_id,
                )
            except MatrixError as exc:
                if not (_already_invited(exc) or _already_joined(exc)):
                    raise HTTPException(
                        status_code=502,
                        detail="Mesaj kanalı daveti hazırlanamadı; daha sonra tekrar deneyin",
                    ) from exc
            try:
                matrix_client.join_room(current_user.matrix_access_token, channel.matrix_room_id)
            except MatrixError as exc:
                if not _already_joined(exc):
                    raise HTTPException(
                        status_code=502,
                        detail="Mesaj kanalına katılım tamamlanamadı; daha sonra tekrar deneyin",
                    ) from exc

        db.add(ServerMember(user_id=current_user.id, server_id=server.id))
        default_role = next((role for role in server.roles if role.is_default), None)
        if default_role and default_role not in current_user.roles:
            current_user.roles.append(default_role)

    invite.status = "accepted"
    db.add(invite)
    db.commit()
    db.refresh(server)
    notify_social_event(invite.inviter_id, "server-invite-accepted")
    notify_social_event(current_user.id, "server-membership-changed")
    return server


@router.delete("/{invite_id}", status_code=204)
def decline_or_cancel_server_invite(
    invite_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invite = _participating_invite(db, invite_id, current_user.id)
    if invite.status != "pending":
        raise HTTPException(status_code=409, detail="Bu davet artık beklemiyor")
    invite.status = "rejected" if invite.invitee_id == current_user.id else "cancelled"
    other_user_id = (
        invite.inviter_id if invite.invitee_id == current_user.id else invite.invitee_id
    )
    db.add(invite)
    db.commit()
    notify_social_event(other_user_id, "server-invite-updated")
