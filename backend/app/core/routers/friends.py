from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.models import Friendship, User
from app.core.routers.gateway import notify_social_event
from app.database import get_db

router = APIRouter(prefix="/friends", tags=["friends"])


def _pair(user_a: int, user_b: int) -> tuple[int, int]:
    return (user_a, user_b) if user_a < user_b else (user_b, user_a)


def _public(user: User) -> schemas.PublicUserRead:
    return schemas.PublicUserRead.model_validate(user)


def _get_participating_request(db: Session, friendship_id: int, user_id: int) -> Friendship:
    friendship = db.get(Friendship, friendship_id)
    if not friendship or user_id not in (friendship.user_low_id, friendship.user_high_id):
        raise HTTPException(status_code=404, detail="Arkadaşlık isteği bulunamadı")
    return friendship


@router.get("", response_model=list[schemas.FriendRead])
def list_friends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendships = (
        db.query(Friendship)
        .filter(
            Friendship.status == "accepted",
            or_(
                Friendship.user_low_id == current_user.id,
                Friendship.user_high_id == current_user.id,
            ),
        )
        .order_by(Friendship.updated_at.desc())
        .all()
    )
    return [
        schemas.FriendRead(
            friendship_id=item.id,
            user=_public(item.other_user(current_user.id)),
            since=item.updated_at,
        )
        for item in friendships
    ]


@router.get("/requests", response_model=schemas.FriendRequestList)
def list_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    requests = (
        db.query(Friendship)
        .filter(
            Friendship.status == "pending",
            or_(
                Friendship.user_low_id == current_user.id,
                Friendship.user_high_id == current_user.id,
            ),
        )
        .order_by(Friendship.created_at.desc())
        .all()
    )
    incoming: list[schemas.FriendRequestRead] = []
    outgoing: list[schemas.FriendRequestRead] = []
    for item in requests:
        direction = "outgoing" if item.requested_by_id == current_user.id else "incoming"
        read = schemas.FriendRequestRead(
            id=item.id,
            user=_public(item.other_user(current_user.id)),
            direction=direction,
            created_at=item.created_at,
        )
        (outgoing if direction == "outgoing" else incoming).append(read)
    return schemas.FriendRequestList(incoming=incoming, outgoing=outgoing)


@router.post("/requests", response_model=schemas.FriendRequestRead, status_code=201)
def create_request(
    payload: schemas.FriendRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    username = payload.username.strip()
    target = db.query(User).filter(User.username.ilike(username), User.is_active.is_(True)).first()
    if not target:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="Kendinize arkadaşlık isteği gönderemezsiniz")

    low_id, high_id = _pair(current_user.id, target.id)
    existing = (
        db.query(Friendship)
        .filter(Friendship.user_low_id == low_id, Friendship.user_high_id == high_id)
        .first()
    )
    if existing:
        detail = (
            "Bu kullanıcı zaten arkadaşınız"
            if existing.status == "accepted"
            else "Bu kullanıcıyla bekleyen bir arkadaşlık isteği var"
        )
        raise HTTPException(status_code=409, detail=detail)

    friendship = Friendship(
        user_low_id=low_id,
        user_high_id=high_id,
        requested_by_id=current_user.id,
        status="pending",
    )
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    notify_social_event(target.id, "friend-request")
    return schemas.FriendRequestRead(
        id=friendship.id,
        user=_public(target),
        direction="outgoing",
        created_at=friendship.created_at,
    )


@router.post("/requests/{friendship_id}/accept", response_model=schemas.FriendRead)
def accept_request(
    friendship_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendship = _get_participating_request(db, friendship_id, current_user.id)
    if friendship.status != "pending":
        raise HTTPException(status_code=409, detail="Bu istek artık beklemiyor")
    if friendship.requested_by_id == current_user.id:
        raise HTTPException(status_code=403, detail="Kendi gönderdiğiniz isteği kabul edemezsiniz")
    friendship.status = "accepted"
    db.add(friendship)
    db.commit()
    db.refresh(friendship)
    notify_social_event(friendship.requested_by_id, "friend-accepted")
    return schemas.FriendRead(
        friendship_id=friendship.id,
        user=_public(friendship.other_user(current_user.id)),
        since=friendship.updated_at,
    )


@router.delete("/{friendship_id}", status_code=204)
def remove_friendship(
    friendship_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    friendship = _get_participating_request(db, friendship_id, current_user.id)
    other_id = (
        friendship.user_high_id
        if friendship.user_low_id == current_user.id
        else friendship.user_low_id
    )
    db.delete(friendship)
    db.commit()
    notify_social_event(other_id, "friend-removed")
