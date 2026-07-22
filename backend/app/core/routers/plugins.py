from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import schemas
from app.core.auth import get_current_user
from app.core.models import Plugin, User
from app.database import get_db
from app.plugins_engine.context import PluginContext
from app.plugins_engine.loader import PluginLoadError, discover_manifests, plugin_registry
from app.plugins_engine.sandbox import PluginSandboxError

router = APIRouter(prefix="/plugins", tags=["plugins"])

# Not: platform genelinde bir "admin" rolü henüz yok (bkz. ROADMAP); şimdilik herhangi bir
# giriş yapmış kullanıcı plugin kurup kaldırabilir. Gerçek yetkilendirme sonraki bir adım.


@router.get("", response_model=list[schemas.PluginManifestRead])
def list_plugins(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    manifests = discover_manifests()
    installed = {p.name: p for p in db.query(Plugin).all()}

    return [
        schemas.PluginManifestRead(
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            permissions=manifest.permissions,
            commands=manifest.commands,
            installed=name in installed,
            enabled=bool(installed.get(name) and installed[name].enabled),
        )
        for name, manifest in manifests.items()
    ]


@router.post("/{name}/install", response_model=schemas.PluginManifestRead)
def install_plugin(name: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    manifest = discover_manifests().get(name)
    if not manifest:
        raise HTTPException(status_code=404, detail="Plugin bulunamadı (plugins/ altında plugin.json yok)")

    try:
        plugin_registry.load(manifest)
    except PluginLoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record = db.query(Plugin).filter(Plugin.name == name).first()
    if record:
        record.enabled = True
        record.version = manifest.version
    else:
        db.add(Plugin(name=manifest.name, version=manifest.version, enabled=True))
    db.commit()

    return schemas.PluginManifestRead(
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        permissions=manifest.permissions,
        commands=manifest.commands,
        installed=True,
        enabled=True,
    )


@router.post("/{name}/uninstall")
def uninstall_plugin(name: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    plugin_registry.unload(name)
    record = db.query(Plugin).filter(Plugin.name == name).first()
    if record:
        record.enabled = False
        db.commit()
    return {"status": "ok"}


@router.post("/commands/run", response_model=schemas.PluginCommandResult)
def run_command(payload: schemas.PluginCommandRequest, current_user: User = Depends(get_current_user)):
    result = plugin_registry.get_handler(payload.command)
    if not result:
        raise HTTPException(status_code=404, detail=f"'{payload.command}' komutu için kurulu/etkin plugin yok")
    plugin_name, handler = result

    context = PluginContext(
        command=payload.command, args=payload.args, user_id=current_user.id, username=current_user.username
    )
    try:
        output = handler(context)
    except PluginSandboxError as exc:
        raise HTTPException(status_code=503, detail="Plugin sandbox kullanılamıyor") from exc
    except Exception as exc:  # plugin kodu güvenilmez; çökmesi Core API'yi düşürmemeli
        raise HTTPException(status_code=500, detail=f"Plugin çalıştırma hatası: {exc}") from exc

    return schemas.PluginCommandResult(plugin=plugin_name, command=payload.command, output=str(output))
