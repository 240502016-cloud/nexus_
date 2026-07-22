from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member, ensure_server_owner
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Channel, Server, User
from app.database import get_db

router = APIRouter(prefix="/servers/{server_id}/channels", tags=["channels"])


@router.post("", response_model=schemas.ChannelRead, status_code=201)
def create_channel(
    server_id: int,
    payload: schemas.ChannelCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)

    owner = server.owner
    if not owner.matrix_access_token:
        raise HTTPException(status_code=409, detail="Sunucu sahibinin Matrix hesabı yok")

    try:
        room_id = matrix_client.create_room(owner.matrix_access_token, name=payload.name)
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=f"Matrix odası oluşturulamadı: {exc}") from exc

    channel = Channel(
        server_id=server.id,
        name=payload.name,
        type=payload.type,
        topic=payload.topic,
        position=payload.position,
        matrix_room_id=room_id,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.get("", response_model=list[schemas.ChannelRead])
def list_channels(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, current_user)
    return server.channels
