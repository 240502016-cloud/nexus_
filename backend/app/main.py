import asyncio

from fastapi import FastAPI

from app.core import models  # noqa: F401  (Base.metadata'ya kaydetmek için import edilir)
from app.core.event_loop import set_main_loop
from app.core.models import Plugin
from app.core.routers import auth, bots, channels, members, messages, plugins, servers, users, voice
from app.database import SessionLocal
from app.plugins_engine.loader import PluginLoadError, discover_manifests, plugin_registry
from app.services.ollama import models as ollama_models  # noqa: F401  (Base.metadata'ya kaydedilir)
from app.services.ollama.requests import router as ai_router

app = FastAPI(title="Nexus Core API")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(servers.router)
app.include_router(channels.router)
app.include_router(members.router)
app.include_router(messages.router)
app.include_router(plugins.router)
app.include_router(bots.router)
app.include_router(bots.server_bots_router)
app.include_router(ai_router)
app.include_router(voice.router)


def _reload_enabled_plugins() -> None:
    """Sunucu yeniden başladığında daha önce install edilmiş plugin'leri belleğe geri yükler."""
    manifests = discover_manifests()
    db = SessionLocal()
    try:
        for record in db.query(Plugin).filter(Plugin.enabled.is_(True)).all():
            manifest = manifests.get(record.name)
            if manifest is None:
                continue  # plugin.json diskten silinmiş olabilir; DB kaydı sessizce atlanır
            try:
                plugin_registry.load(manifest)
            except PluginLoadError:
                pass  # bozuk plugin, diğerlerini etkilemeden atlanır
    finally:
        db.close()


@app.on_event("startup")
async def on_startup() -> None:
    # Şema, Compose'taki tek-seferlik `migrate` servisi tarafından Alembic ile hazırlanır.
    # Uygulama başlangıcında create_all çalıştırmak production'da kontrolsüz schema değişikliğine
    # ve migration geçmişinin atlanmasına yol açar.
    _reload_enabled_plugins()
    # music plugin'i gibi async iş gerektiren plugin'lerin senkron thread'lerden bu loop'a
    # iş verebilmesi için (bkz. app/core/event_loop.py).
    set_main_loop(asyncio.get_running_loop())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
