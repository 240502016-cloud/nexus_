from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member, ensure_server_owner
from app.core.models import Role, Server, ServerMember, User
from app.core.permissions import Permission
from app.database import get_db

router = APIRouter(prefix="/servers", tags=["servers"])


@router.post("", response_model=schemas.ServerRead, status_code=201)
def create_server(
    payload: schemas.ServerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = Server(
        name=payload.name, description=payload.description, icon_url=payload.icon_url, owner_id=current_user.id
    )
    db.add(server)
    db.flush()

    default_role = Role(
        server_id=server.id, name="@everyone", is_default=True, permissions=int(Permission.default())
    )
    db.add(default_role)
    db.flush()

    db.add(ServerMember(user_id=current_user.id, server_id=server.id))
    current_user.roles.append(default_role)

    db.commit()
    db.refresh(server)
    return server


@router.get("", response_model=list[schemas.ServerRead])
def list_my_servers(current_user: User = Depends(get_current_user)):
    return [membership.server for membership in current_user.memberships]


@router.get("/{server_id}", response_model=schemas.ServerRead)
def get_server(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, current_user)
    return server


@router.patch("/{server_id}", response_model=schemas.ServerRead)
def update_server(
    server_id: int,
    payload: schemas.ServerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sunucu adını/açıklamasını günceller (yalnızca sahip)."""
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)
    if payload.name is not None:
        server.name = payload.name.strip()
    if payload.description is not None:
        server.description = payload.description.strip() or None
    db.add(server)
    db.commit()
    db.refresh(server)
    return server


@router.delete("/{server_id}", status_code=204)
def delete_server(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sunucuyu siler (yalnızca sahip). Kanallar/üyeler/roller DB cascade ile silinir."""
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)
    # Bağımlı kayıtlar FK'da ON DELETE CASCADE; çekirdek DELETE ile DB cascade tetiklenir.
    db.execute(delete(Server).where(Server.id == server_id))
    db.commit()
