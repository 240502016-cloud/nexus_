from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Callable

from app.config import settings
from app.plugins_engine.manifest import PluginManifest
from app.plugins_engine.sandbox import execute_in_sandbox

# backend/app/plugins_engine/loader.py -> proje kökü/plugins
PLUGINS_DIR = Path(__file__).resolve().parents[3] / "plugins"


class PluginLoadError(RuntimeError):
    pass


_ENTRY_POINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:[A-Za-z_][A-Za-z0-9_]*$")


def discover_manifests() -> dict[str, PluginManifest]:
    """plugins/ altındaki her klasörü tarar, plugin.json'ları okur ve doğrular."""
    manifests: dict[str, PluginManifest] = {}
    if not PLUGINS_DIR.exists():
        return manifests

    for entry in sorted(PLUGINS_DIR.iterdir()):
        manifest_path = entry / "plugin.json"
        if not entry.is_dir() or not manifest_path.exists():
            continue
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests[entry.name] = PluginManifest(**data)
    return manifests


def _load_module(plugin_dir: Path, module_filename: str) -> ModuleType:
    module_path = plugin_dir / f"{module_filename}.py"
    if not module_path.exists():
        raise PluginLoadError(f"Plugin modülü bulunamadı: {module_path}")

    spec = importlib.util.spec_from_file_location(f"nexus_plugin_{plugin_dir.name}", module_path)
    if spec is None or spec.loader is None:
        raise PluginLoadError(f"Plugin modülü yüklenemedi: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_handler(manifest: PluginManifest) -> Callable:
    """manifest.entry_point ('main:handle_command') içindeki fonksiyonu yükler."""
    module_name, _, func_name = manifest.entry_point.partition(":")
    if not module_name or not func_name:
        raise PluginLoadError(f"Geçersiz entry_point: {manifest.entry_point!r} (beklenen: 'modül:fonksiyon')")

    plugin_dir = PLUGINS_DIR / manifest.name
    module = _load_module(plugin_dir, module_name)
    handler = getattr(module, func_name, None)
    if handler is None or not callable(handler):
        raise PluginLoadError(f"'{func_name}' fonksiyonu {module_name}.py içinde bulunamadı")
    return handler


def _validate_manifest_entry_point(manifest: PluginManifest) -> None:
    if not _ENTRY_POINT_RE.fullmatch(manifest.entry_point):
        raise PluginLoadError(
            f"Geçersiz entry_point: {manifest.entry_point!r} (beklenen: 'modül:fonksiyon')"
        )


def _sandbox_handler(manifest: PluginManifest) -> Callable:
    _validate_manifest_entry_point(manifest)

    def run(context: object) -> object:
        return execute_in_sandbox(manifest, context)

    return run


class PluginRegistry:
    """Etkinleştirilmiş plugin'lerin bellekteki kayıt defteri.

    Bir plugin sadece install edildiğinde buraya yüklenir; plugin kodundaki bir hata
    (import veya çalışma zamanı) sadece o plugin'i etkiler, core platformu düşürmez —
    çağıran taraf (routers/plugins.py) PluginLoadError ve çalışma zamanı hatalarını yakalar.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, tuple[str, Callable]] = {}  # command -> (plugin_name, handler)
        self._loaded_plugins: set[str] = set()

    def load(self, manifest: PluginManifest) -> None:
        # Production never imports third-party plugin code into the Core API process.
        # The local path remains available only when explicitly selected for development.
        handler = (
            load_handler(manifest)
            if settings.plugin_execution_mode == "local"
            else _sandbox_handler(manifest)
        )
        for command in manifest.commands:
            self._handlers[command] = (manifest.name, handler)
        self._loaded_plugins.add(manifest.name)

    def unload(self, plugin_name: str) -> None:
        self._handlers = {
            command: (name, handler) for command, (name, handler) in self._handlers.items() if name != plugin_name
        }
        self._loaded_plugins.discard(plugin_name)

    def is_loaded(self, plugin_name: str) -> bool:
        return plugin_name in self._loaded_plugins

    def get_handler(self, command: str) -> tuple[str, Callable] | None:
        return self._handlers.get(command)


plugin_registry = PluginRegistry()
