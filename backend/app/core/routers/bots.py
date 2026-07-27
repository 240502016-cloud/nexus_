import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.authz import ensure_server_member, ensure_server_owner
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Bot, BotPluginLink, BotServerLink, Plugin, Server, User
from app.database import get_db
from app.plugins_engine.loader import discover_manifests

router = APIRouter(prefix="/bots", tags=["bots"])

# Not: platform admin rolü henüz yok; herhangi bir giriş yapmış kullanıcı bot oluşturabilir
# (users.py/plugins.py'deki aynı geçici kısıtlamayla tutarlı, bkz. ROADMAP).


@router.post("", response_model=schemas.BotRead, status_code=201)
def create_bot(
    payload: schemas.BotCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if db.query(Bot).filter(Bot.name == payload.name).first():
        raise HTTPException(status_code=409, detail="Bu isimde bir bot zaten var")

    # Bot bir parolayla giriş yapmaz; sadece Matrix'in döndürdüğü access_token saklanır.
    throwaway_password = uuid.uuid4().hex
    try:
        matrix_account = matrix_client.register_user(f"bot.{payload.name}", throwaway_password)
    except MatrixError as exc:
        raise HTTPException(status_code=502, detail=f"Bot için Matrix hesabı oluşturulamadı: {exc}") from exc

    bot = Bot(
        name=payload.name,
        command_prefix=payload.command_prefix,
        matrix_user_id=matrix_account["user_id"],
        matrix_access_token=matrix_account["access_token"],
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@router.get("", response_model=list[schemas.BotRead])
def list_bots(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Bot).all()


@router.post("/{bot_id}/servers/{server_id}", status_code=201)
def add_bot_to_server(
    bot_id: int,
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)

    bot = db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot bulunamadı")
    if not bot.matrix_access_token:
        raise HTTPException(status_code=409, detail="Botun Matrix hesabı yok")

    existing = db.get(BotServerLink, {"bot_id": bot.id, "server_id": server.id})
    if existing:
        raise HTTPException(status_code=409, detail="Bot zaten bu sunucuya eklenmiş")

    owner = server.owner
    for channel in server.channels:
        if not channel.matrix_room_id:
            continue
        try:
            matrix_client.invite_user(owner.matrix_access_token, channel.matrix_room_id, bot.matrix_user_id)
            matrix_client.join_room(bot.matrix_access_token, channel.matrix_room_id)
        except MatrixError as exc:
            raise HTTPException(status_code=502, detail=f"Bot kanala eklenemedi: {exc}") from exc

    db.add(BotServerLink(bot_id=bot.id, server_id=server.id))
    db.commit()
    return {"status": "ok"}


server_bots_router = APIRouter(prefix="/servers/{server_id}/bots", tags=["bots"])


@router.delete("/{bot_id}/servers/{server_id}", status_code=204)
def remove_bot_from_server(
    bot_id: int,
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)
    link = db.get(BotServerLink, {"bot_id": bot_id, "server_id": server_id})
    if link:
        bot = link.bot
        if bot.matrix_access_token:
            for channel in server.channels:
                if not channel.matrix_room_id:
                    continue
                try:
                    matrix_client.leave_room(bot.matrix_access_token, channel.matrix_room_id)
                except MatrixError:
                    pass
        db.delete(link)
        db.commit()


@server_bots_router.get("", response_model=list[schemas.BotRead])
def list_server_bots(
    server_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, current_user)

    links = db.query(BotServerLink).filter(BotServerLink.server_id == server_id).all()
    return [link.bot for link in links]


def _get_owned_server_bot(db: Session, server_id: int, bot_id: int, current_user: User) -> Bot:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_owner(server, current_user)
    link = db.get(BotServerLink, {"bot_id": bot_id, "server_id": server_id})
    if not link:
        raise HTTPException(status_code=404, detail="Bot bu sunucuda değil")
    return link.bot


@server_bots_router.post("/{bot_id}/plugins/{plugin_name}", status_code=201)
def link_plugin_to_bot(
    server_id: int,
    bot_id: int,
    plugin_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_server_bot(db, server_id, bot_id, current_user)
    manifest = discover_manifests().get(plugin_name)
    record = db.query(Plugin).filter(Plugin.name == plugin_name, Plugin.enabled.is_(True)).first()
    if not manifest or not record:
        raise HTTPException(status_code=409, detail="Plugin önce kurulup etkinleştirilmeli")
    if not manifest.requires_bot_link:
        raise HTTPException(status_code=409, detail="Bu plugin bota özel bağlantı gerektirmiyor")

    occupied = (
        db.query(BotPluginLink)
        .join(BotServerLink, BotServerLink.bot_id == BotPluginLink.bot_id)
        .filter(
            BotServerLink.server_id == server_id,
            BotPluginLink.plugin_name == plugin_name,
            BotPluginLink.bot_id != bot.id,
        )
        .first()
    )
    if occupied:
        raise HTTPException(status_code=409, detail="Bu plugin sunucuda başka bir bota bağlı")

    existing = db.get(BotPluginLink, {"bot_id": bot.id, "plugin_name": plugin_name})
    if not existing:
        db.add(BotPluginLink(bot_id=bot.id, plugin_name=plugin_name))
        db.commit()
    return {"status": "ok"}


@server_bots_router.delete("/{bot_id}/plugins/{plugin_name}", status_code=204)
def unlink_plugin_from_bot(
    server_id: int,
    bot_id: int,
    plugin_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bot = _get_owned_server_bot(db, server_id, bot_id, current_user)
    link = db.get(BotPluginLink, {"bot_id": bot.id, "plugin_name": plugin_name})
    if link:
        db.delete(link)
        db.commit()
