from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Bot, BotServerLink, Channel
from app.core.rate_limit import RateLimiter
from app.plugins_engine.context import PluginContext
from app.plugins_engine.loader import plugin_registry
from app.services.ollama.models import QueuedAiResponse

# Kullanıcı başına 10 saniyede en fazla 5 komut - plugin'lerin (özellikle Ollama gibi
# CPU/GPU maliyeti olanların) mesaj spam'iyle kötüye kullanılmasını önler.
_command_limiter = RateLimiter(max_calls=5, window_seconds=10)

# Serbest metinle sohbet edilebilecek "varsayılan" komut - bir bot @mention edilip ardından
# tanınan bir komut adı gelmezse, kalan metnin tamamı bu komuta arg olarak gönderilir
# (ai_assistant kuruluysa gerçek bir sohbete dönüşür).
_FREEFORM_FALLBACK_COMMAND = "sor"


@dataclass
class MessageEvent:
    """Bir kanala mesaj gönderildiğinde oluşan olay.

    Bot Engine'in şu an dinlediği tek olay tipi bu; katılma/ayrılma gibi diğer olaylar
    (bkz. ARCHITECTURE.md) ileride eklenecek. Mesaj gönderme uç noktasından (routers/messages.py)
    tetiklenir; AI `/sor` komutu ayrı PostgreSQL worker kuyruğuna bırakılır, diğer plugin'ler
    mevcut senkron MVP akışını kullanır.
    """

    channel: Channel
    sender_id: int
    sender_username: str
    content: str


@dataclass
class BotReply:
    bot_name: str
    content: str
    send_matrix: bool = True


def parse_command(content: str, prefix: str) -> tuple[str, str] | None:
    """'/sunucu-durumu bir arg' -> ('sunucu-durumu', 'bir arg'). Komut değilse None."""
    if not content.startswith(prefix):
        return None
    body = content[len(prefix) :].strip()
    if not body:
        return None
    command, _, args = body.partition(" ")
    return command, args.strip()


def parse_mention(content: str, bot_names: list[str]) -> tuple[str, str] | None:
    """'@nexus-bot sunucu-durumu' -> ('nexus-bot', 'sunucu-durumu'). Mention değilse None.

    Sadece mesajın en başındaki @isim eşleşir (bot_names'teki isimlerden biriyle, büyük/küçük
    harf duyarsız); eşleşmezse (ör. bir insanı etiketliyorsa) mention olarak sayılmaz.
    """
    if not content.startswith("@"):
        return None
    name, _, rest = content[1:].partition(" ")
    name_lower = name.lower()
    for bot_name in bot_names:
        if bot_name.lower() == name_lower:
            return bot_name, rest.strip()
    return None


def _run_command(
    db: Session, bot: Bot, event: MessageEvent, command: str, args: str
) -> BotReply:
    handler_entry = plugin_registry.get_handler(command)
    if not handler_entry:
        output = f"'{command}' komutunu tanımıyorum."
    elif not _command_limiter.allow(str(event.sender_id)):
        output = "Çok hızlı komut gönderiyorsunuz, birkaç saniye bekleyin."
    else:
        _plugin_name, handler = handler_entry
        context = PluginContext(
            command=command,
            args=args,
            user_id=event.sender_id,
            username=event.sender_username,
            channel_id=event.channel.id,
            matrix_room_id=event.channel.matrix_room_id,
            server_id=event.channel.server_id,
            bot_id=bot.id,
            bot_name=bot.name,
        )
        try:
            raw_output = handler(context)
            if isinstance(raw_output, QueuedAiResponse):
                return BotReply(
                    bot_name=bot.name,
                    content=f"AI isteği kuyruğa alındı (job_id={raw_output.job_id}).",
                    send_matrix=False,
                )
            output = str(raw_output)
        except Exception as exc:  # plugin kodu güvenilmez; botun cevap veremediğini bildir
            output = f"({bot.name} hata: {exc})"

    if bot.matrix_access_token and event.channel.matrix_room_id and not isinstance(output, QueuedAiResponse):
        try:
            matrix_client.send_message(bot.matrix_access_token, event.channel.matrix_room_id, output)
        except MatrixError:
            pass  # Matrix'e yazılamadı; yine de replies listesinde görünür

    return BotReply(bot_name=bot.name, content=output)


def handle_message_event(db: Session, event: MessageEvent) -> list[BotReply]:
    """Sunucuya eklenmiş botlar arasında komutla eşleşeni bulup çalıştırır; botun kendi
    Matrix hesabıyla cevabı odaya yazar (bot yetki kontrolü: bir bot yalnızca BotServerLink
    ile eklendiği sunucularda komuta cevap verir).

    İki hitap biçimi var:
    - '/komut arg' — sunucudaki AKTİF her bot dener (aynı komutu birden fazla bot yüklüyse
      hepsi cevap verir, bu bilinçli bir davranış).
      - '@bot-adı komut arg' — SADECE o bota yönlendirilir, diğerleri sessiz kalır. Komut adı
      tanınmıyorsa (serbest metin), 'sor' komutuna (ai_assistant kuruluysa) yönlendirilir -
      "@nexus-bot türkiye'nin başkenti neresi" gibi doğal bir sohbeti mümkün kılar.
    """
    bot_links = [link for link in db.query(BotServerLink).filter(BotServerLink.server_id == event.channel.server_id) if link.bot.is_active]
    if not bot_links:
        return []

    mention = parse_mention(event.content, [link.bot.name for link in bot_links])
    if mention:
        mentioned_name, remainder = mention
        bot = next(link.bot for link in bot_links if link.bot.name.lower() == mentioned_name.lower())

        first_word, _, rest = remainder.partition(" ")
        if first_word and plugin_registry.get_handler(first_word):
            command, args = first_word, rest.strip()
        elif plugin_registry.get_handler(_FREEFORM_FALLBACK_COMMAND):
            command, args = _FREEFORM_FALLBACK_COMMAND, remainder
        else:
            return [BotReply(bot_name=bot.name, content=f"'{remainder}' komutunu tanımıyorum.")]

        return [_run_command(db, bot, event, command, args)]

    replies: list[BotReply] = []
    for link in bot_links:
        bot = link.bot
        parsed = parse_command(event.content, bot.command_prefix)
        if not parsed:
            continue
        command, args = parsed
        if not plugin_registry.get_handler(command):
            continue
        replies.append(_run_command(db, bot, event, command, args))

    return replies
