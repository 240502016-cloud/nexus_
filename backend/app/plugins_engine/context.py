from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PluginContext:
    """Plugin API'nin ilk hali: bir komut çalıştığında plugin'e verilen bağlam.

    channel_id/matrix_room_id/server_id sadece komut bir kanaldan (Bot Engine üzerinden)
    tetiklendiğinde doludur; POST /plugins/commands/run ile doğrudan çalıştırmada None'dır.
    """

    command: str
    args: str
    user_id: int
    username: str
    channel_id: int | None = None
    matrix_room_id: str | None = None
    server_id: int | None = None
    # Komutu hangi botun çalıştırdığı - çoğu plugin bunu kullanmaz (dispatcher cevabı zaten
    # botun kendi Matrix hesabıyla gönderiyor). music gibi bot kimliğine ihtiyaç duyan
    # plugin'ler için (ör. sesli kanalda hangi katılımcı olarak görüneceğini belirlemek).
    bot_id: int | None = None
    bot_name: str | None = None
