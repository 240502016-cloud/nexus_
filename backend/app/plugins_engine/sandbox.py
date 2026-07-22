"""Client for the isolated plugin-sandbox sidecar.

The Core API never imports untrusted plugin modules in sandbox mode. It sends only the
small, JSON-serializable :class:`PluginContext` to a dedicated container, which runs the
plugin in a short-lived subprocess with a timeout and no database credentials.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

import requests

from app.config import settings
from app.plugins_engine.context import PluginContext
from app.plugins_engine.manifest import PluginManifest


class PluginSandboxError(RuntimeError):
    """Controlled failure while talking to the plugin sandbox."""


def execute_in_sandbox(manifest: PluginManifest, context: PluginContext) -> Any:
    """Execute one plugin command through the sidecar and return its JSON result."""
    if not settings.plugin_sandbox_url:
        raise PluginSandboxError("Plugin sandbox adresi yapılandırılmamış")
    if not settings.plugin_sandbox_api_key:
        raise PluginSandboxError("Plugin sandbox API anahtarı yapılandırılmamış")

    payload = {
        "entry_point": manifest.entry_point,
        "context": asdict(context) if is_dataclass(context) else context,
    }
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    if len(serialized_payload.encode("utf-8")) > settings.plugin_sandbox_max_payload_bytes:
        raise PluginSandboxError("Plugin sandbox isteği çok büyük")
    try:
        response = requests.post(
            f"{settings.plugin_sandbox_url.rstrip('/')}/v1/execute/{manifest.name}",
            headers={
                "Authorization": f"Bearer {settings.plugin_sandbox_api_key}",
                "Content-Type": "application/json",
            },
            data=serialized_payload,
            timeout=max(0.1, settings.plugin_sandbox_timeout_seconds),
        )
    except requests.Timeout as exc:
        raise PluginSandboxError("Plugin sandbox zaman aşımına uğradı") from exc
    except requests.RequestException as exc:
        raise PluginSandboxError("Plugin sandbox'a ulaşılamadı") from exc

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except (ValueError, AttributeError):
            detail = response.text
        raise PluginSandboxError(str(detail)[:500])

    try:
        result = response.json()
    except ValueError as exc:
        raise PluginSandboxError("Plugin sandbox geçersiz JSON döndürdü") from exc
    if not isinstance(result, dict) or "output" not in result:
        raise PluginSandboxError("Plugin sandbox yanıtı geçersiz")
    return result["output"]
