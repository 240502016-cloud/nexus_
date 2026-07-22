from __future__ import annotations

from pydantic import BaseModel


class PluginManifest(BaseModel):
    """plugins/<isim>/plugin.json dosyasının şeması."""

    name: str
    version: str
    description: str | None = None
    entry_point: str  # "main:handle_command" -> <modül dosyası>:<fonksiyon>
    permissions: list[str] = []
    commands: list[str] = []
