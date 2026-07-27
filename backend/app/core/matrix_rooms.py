from __future__ import annotations

from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import User


def is_not_in_room_error(exc: MatrixError) -> bool:
    text = str(exc).casefold()
    return "not in room" in text or "not joined" in text


def invite_and_join(room_id: str, owner: User, member: User) -> None:
    """Bir kullanıcıyı özel Matrix odasına ekler; uygulama token'larını dışarı sızdırmaz."""
    if member.id == owner.id:
        return
    if not owner.matrix_access_token or not member.matrix_access_token or not member.matrix_user_id:
        raise MatrixError("Matrix oda üyeliği için kullanıcı hesabı eksik")
    matrix_client.invite_user(owner.matrix_access_token, room_id, member.matrix_user_id)
    matrix_client.join_room(member.matrix_access_token, room_id)


def repair_room_membership(room_id: str, owner: User, member: User) -> None:
    """Eski/sonradan açılmış odalarda eksik üyeliği davet+join ile kendiliğinden onarır."""
    if member.id == owner.id:
        return
    invite_and_join(room_id, owner, member)
