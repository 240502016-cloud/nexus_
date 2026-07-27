"""Şans oyunu komutlarını güvenli Core servisine ileten sandbox adaptörü.

Plugin sandbox'ın veritabanı yetkisi yoktur. Bu dosya yalnızca doğrulanabilir bir eylem
zarfı üretir; davet, gizli hamle ve çark durumu Core API tarafından yetki kontrollü olarak
PostgreSQL'de işlenir.
"""

import json


ACTION_PREFIX = "NEXUS_CHANCE_ACTION:"


def handle_command(context) -> str:
    if context.server_id is None or context.channel_id is None:
        return "Bu komut yalnızca bir sunucu kanalında, bota bağlıyken çalıştırılabilir."
    payload = {
        "version": 1,
        "command": context.command,
        "args": context.args or "",
    }
    return ACTION_PREFIX + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
