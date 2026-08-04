import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import models  # noqa: F401  (Base.metadata'ya kaydetmek için import edilir)
from app.core.event_loop import set_main_loop
from app.core.models import Plugin
from app.core.routers import (
    auth,
    attachments,
    bots,
    channels,
    direct,
    friends,
    gateway,
    join_codes,
    members,
    messages,
    plugins,
    servers,
    server_invites,
    users,
    voice,
)
from app.database import SessionLocal
from app.modules.party_lore import models as party_lore_models  # noqa: F401
from app.modules.party_lore.router import router as party_lore_router
from app.modules.ai_commentator import models as ai_commentator_models  # noqa: F401
from app.modules.ai_commentator.router import router as ai_commentator_router
from app.modules.meme_generator import models as meme_generator_models  # noqa: F401
from app.modules.meme_generator.router import router as meme_generator_router
from app.modules.highlight_generator import models as highlight_generator_models  # noqa: F401
from app.modules.highlight_generator.router import router as highlight_generator_router
from app.modules.ai_roast_battle import models as ai_roast_battle_models  # noqa: F401
from app.modules.ai_roast_battle.router import router as ai_roast_battle_router
from app.plugins_engine.loader import PluginLoadError, discover_manifests, plugin_registry
from app.platform import models as platform_models  # noqa: F401
from app.platform.router import router as experiences_router
from app.services.ollama import models as ollama_models  # noqa: F401  (Base.metadata'ya kaydedilir)
from app.services.ollama.requests import router as ai_router

app = FastAPI(title="Nexus Core API")

# Paketlenmiş istemci yerel ve güvenli bir özel origin kullanır. Yalnız bu origin'e API erişimi
# verilir; wildcard kullanılmaz ve web istemcisi production'da aynı-origin çalışmaya devam eder.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["nexus://app"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

app.include_router(auth.router)
app.include_router(attachments.router)
app.include_router(users.router)
app.include_router(servers.router)
app.include_router(server_invites.router)
app.include_router(channels.router)
app.include_router(members.router)
app.include_router(messages.router)
app.include_router(friends.router)
app.include_router(direct.router)
app.include_router(plugins.router)
app.include_router(bots.router)
app.include_router(bots.server_bots_router)
app.include_router(ai_router)
app.include_router(voice.router)
app.include_router(gateway.router)
app.include_router(join_codes.router)
app.include_router(experiences_router)
app.include_router(party_lore_router)
app.include_router(ai_commentator_router)
app.include_router(meme_generator_router)
app.include_router(highlight_generator_router)
app.include_router(ai_roast_battle_router)


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
