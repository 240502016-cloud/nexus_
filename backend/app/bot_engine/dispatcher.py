from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Bot, BotPluginLink, BotServerLink, Channel
from app.core.rate_limit import RateLimiter
from app.plugins_engine.context import PluginContext
from app.plugins_engine.loader import RegisteredCommand, plugin_registry
from app.services.chance_games import handle_chance_command, parse_action
from app.services.ollama.models import QueuedAiResponse

# Kullanıcı başına 10 saniyede en fazla 5 komut - plugin'lerin (özellikle Ollama gibi
# CPU/GPU maliyeti olanların) mesaj spam'iyle kötüye kullanılmasını önler.
_command_limiter = RateLimiter(max_calls=20, window_seconds=10)

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
    event_id: str | None = None
    matrix_user_id: str | None = None


def parse_command(content: str, prefix: str) -> tuple[str, str] | None:
    """'/sunucu-durumu bir arg' -> ('sunucu-durumu', 'bir arg'). Komut değilse None."""
    if not content.startswith(prefix):
        return None
    body = content[len(prefix) :].strip()
    if not body:
        return None
    command, _, args = body.partition(" ")
    return command.rstrip(":"), args.strip()


def parse_colon_command(content: str) -> tuple[str, str] | None:
    """Açıkça izin veren pluginler için ``ekleçark: elma`` söz dizimini ayrıştırır."""
    command, separator, args = content.partition(":")
    command = command.strip()
    if not separator or not command or not args.strip() or any(char.isspace() for char in command):
        return None
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


def _bot_can_run(db: Session, bot: Bot, entry: RegisteredCommand) -> bool:
    if not entry.requires_bot_link:
        return True
    return (
        db.get(BotPluginLink, {"bot_id": bot.id, "plugin_name": entry.plugin_name})
        is not None
    )


def _send_bot_message_with_room_repair(bot: Bot, event: MessageEvent, output: str) -> str | None:
    if not bot.matrix_access_token or not bot.matrix_user_id or not event.channel.matrix_room_id:
        return None
    try:
        return matrix_client.send_message(
            bot.matrix_access_token,
            event.channel.matrix_room_id,
            output,
        )
    except MatrixError:
        # Bot sunucuya eklendikten sonra açılan metin kanallarında eski bot hesabı Matrix
        # odasına davet edilmemiş olabilir. Komutu görünmez biçimde yutmak yerine üyeliği
        # bir kez onarıp aynı cevabı yeniden gönder.
        owner = event.channel.server.owner
        if not owner.matrix_access_token:
            return None
        try:
            matrix_client.invite_user(
                owner.matrix_access_token,
                event.channel.matrix_room_id,
                bot.matrix_user_id,
            )
        except MatrixError as exc:
            detail = str(exc).casefold()
            if "already" not in detail and "invite" not in detail:
                return None
        try:
            matrix_client.join_room(bot.matrix_access_token, event.channel.matrix_room_id)
        except MatrixError as exc:
            if "already" not in str(exc).casefold():
                return None
        try:
            return matrix_client.send_message(
                bot.matrix_access_token,
                event.channel.matrix_room_id,
                output,
            )
        except MatrixError:
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
        command = handler_entry.command
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
            raw_output = handler_entry.handler(context)
            if isinstance(raw_output, QueuedAiResponse):
                return BotReply(
                    bot_name=bot.name,
                    content=f"AI isteği kuyruğa alındı (job_id={raw_output.job_id}).",
                    send_matrix=False,
                )
            if handler_entry.plugin_name == "chance_games" and parse_action(
                raw_output, command, args
            ):
                output = handle_chance_command(db, context)
            else:
                output = str(raw_output)
        except Exception as exc:  # plugin kodu güvenilmez; botun cevap veremediğini bildir
            output = f"({bot.name} hata: {exc})"

    event_id: str | None = None
    if not isinstance(output, QueuedAiResponse):
        event_id = _send_bot_message_with_room_repair(bot, event, output)

    return BotReply(
        bot_name=bot.name,
        content=output,
        event_id=event_id,
        matrix_user_id=bot.matrix_user_id,
    )


def is_private_message_event(db: Session, event: MessageEvent) -> bool:
    """Mesajın Matrix'e hiç yazılmadan çalıştırılması gereken bot komutu olup olmadığını söyler."""
    bot_links = [
        link
        for link in db.query(BotServerLink).filter(
            BotServerLink.server_id == event.channel.server_id
        )
        if link.bot.is_active
    ]
    if not bot_links:
        return False

    mention = parse_mention(event.content, [link.bot.name for link in bot_links])
    if mention:
        mentioned_name, remainder = mention
        first_word, _, _rest = remainder.partition(" ")
        entry = plugin_registry.get_handler(first_word.rstrip(":")) if first_word else None
        bot = next(
            link.bot for link in bot_links if link.bot.name.casefold() == mentioned_name.casefold()
        )
        return bool(entry and entry.is_private and _bot_can_run(db, bot, entry))

    for link in bot_links:
        parsed = parse_command(event.content, link.bot.command_prefix)
        if not parsed:
            continue
        entry = plugin_registry.get_handler(parsed[0])
        if entry and entry.is_private and _bot_can_run(db, link.bot, entry):
            return True
    return False


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
        entry = plugin_registry.get_handler(first_word.rstrip(":")) if first_word else None
        if entry and _bot_can_run(db, bot, entry):
            command, args = entry.command, rest.strip()
        else:
            fallback = plugin_registry.get_handler(_FREEFORM_FALLBACK_COMMAND)
            if fallback and _bot_can_run(db, bot, fallback):
                command, args = fallback.command, remainder
            else:
                return []

        return [_run_command(db, bot, event, command, args)]

    replies: list[BotReply] = []
    handled_dedicated_plugins: set[str] = set()
    for link in bot_links:
        bot = link.bot
        parsed = parse_command(event.content, bot.command_prefix)
        if not parsed:
            candidate = parse_colon_command(event.content)
            candidate_entry = plugin_registry.get_handler(candidate[0]) if candidate else None
            if candidate and candidate_entry and candidate_entry.allow_colon_syntax:
                parsed = candidate
        if not parsed:
            continue
        command, args = parsed
        entry = plugin_registry.get_handler(command)
        if not entry or not _bot_can_run(db, bot, entry):
            continue
        if entry.requires_bot_link and entry.plugin_name in handled_dedicated_plugins:
            continue
        replies.append(_run_command(db, bot, event, entry.command, args))
        if entry.requires_bot_link:
            handled_dedicated_plugins.add(entry.plugin_name)

    return replies
