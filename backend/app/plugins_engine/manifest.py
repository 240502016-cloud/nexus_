from __future__ import annotations

from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """plugins/<isim>/plugin.json dosyasının şeması."""

    name: str
    version: str
    description: str | None = None
    entry_point: str  # "main:handle_command" -> <modül dosyası>:<fonksiyon>
    permissions: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    # Hamle gibi karşı tarafa görünmemesi gereken komutlar Matrix'e yazılmadan çalıştırılır.
    private_commands: list[str] = Field(default_factory=list)
    # True olduğunda plugin yalnızca açıkça bağlandığı botlarda çalışır.
    requires_bot_link: bool = False
    # "ekleçark: elma" gibi bot prefix'i olmadan kullanılabilen, açıkça izinli komutlar.
    colon_commands: list[str] = Field(default_factory=list)
