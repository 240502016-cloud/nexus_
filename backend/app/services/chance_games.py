from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.models import ChanceGameSession, ChanceWheel, ServerMember, User
from app.plugins_engine.context import PluginContext

ACTION_PREFIX = "NEXUS_CHANCE_ACTION:"
EVENT_PREFIX = "NEXUS_GAME_EVENT:"
INVITE_TTL = timedelta(minutes=2)
ACTIVE_GAME_TTL = timedelta(minutes=5)
MAX_WHEEL_ENTRIES = 50
MAX_WHEEL_WEIGHT = 500

_MENTION_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_.-]{1,32})(?::[^\s]+)?")
_PUBLIC_ID_RE = re.compile(r"^[a-f0-9]{10}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_RPS_COMMANDS = {"taş": "taş", "tas": "taş", "kağıt": "kağıt", "kagit": "kağıt", "makas": "makas"}
_RPS_WINS = {("taş", "makas"), ("makas", "kağıt"), ("kağıt", "taş")}
_GAME_ALIASES = {
    "takama": "rps",
    "taş-kağıt-makas": "rps",
    "tas-kagit-makas": "rps",
    "yazıtura": "coin",
    "yazitura": "coin",
    "yazı-tura": "coin",
    "yazi-tura": "coin",
}
_GAME_LABELS = {"rps": "Taş · Kağıt · Makas", "coin": "Yazı · Tura"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _has_expired(expires_at: datetime) -> bool:
    # SQLite test sürücüsü timezone bilgisini düşürebilir; production PostgreSQL aware döndürür.
    now = _now()
    if expires_at.tzinfo is None:
        now = now.replace(tzinfo=None)
    return expires_at <= now


def _event(event_type: str, text: str, **payload: object) -> str:
    envelope = {"type": event_type, **payload}
    return f"{EVENT_PREFIX}{json.dumps(envelope, ensure_ascii=False, separators=(',', ':'))}\n{text}"


def _plain_help() -> str:
    return (
        "🎲 Şans Ustası komut rehberi\n"
        "• /takama @kullanıcı — Taş Kağıt Makas daveti gönderir\n"
        "• /kabul <davet-kodu> veya /kabul takama @kullanıcı\n"
        "• /reddet <davet-kodu> · /iptal <davet-kodu>\n"
        "• Kabulden sonra /taş, /kağıt veya /makas — hamlen rakip tamamlayana kadar gizlidir\n"
        "• /yazıtura — tek kişilik atış · /yazıtura @kullanıcı — düello\n"
        "• /ekleçark elma veya ekleçark: elma — çarka seçenek ekler\n"
        "• /ekleçark elma | 3 — ağırlıklı seçenek ekler\n"
        "• /çarkliste · /çıkarçark <sıra|ad> · /temizleçark · /çark"
    )


def parse_action(raw_output: object, expected_command: str, expected_args: str) -> bool:
    """Sandbox çıktısının yalnızca bu plugin için üretilmiş, değiştirilmemiş bir eylem olduğunu doğrular."""
    if not isinstance(raw_output, str) or not raw_output.startswith(ACTION_PREFIX):
        return False
    try:
        payload = json.loads(raw_output[len(ACTION_PREFIX) :])
    except (TypeError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("version") == 1
        and payload.get("command") == expected_command
        and payload.get("args") == expected_args
    )


def _expire_stale(db: Session) -> None:
    now = _now()
    stale = (
        db.query(ChanceGameSession)
        .filter(
            ChanceGameSession.status.in_(("pending", "active")),
            ChanceGameSession.expires_at <= now,
        )
        .all()
    )
    if not stale:
        return
    for game in stale:
        game.status = "expired"
        game.completed_at = now
    db.commit()


def _find_server_user(db: Session, server_id: int, mention: str) -> User | None:
    user = db.query(User).filter(func.lower(User.username) == mention.casefold()).first()
    if not user:
        return None
    membership = db.get(ServerMember, {"user_id": user.id, "server_id": server_id})
    if membership:
        return user
    # Sunucu sahibi ilk şemada server_members tablosunda bulunmayabildiği için ayrıca kabul edilir.
    from app.core.models import Server

    server = db.get(Server, server_id)
    return user if server and server.owner_id == user.id else None


def _extract_mention(args: str) -> str | None:
    match = _MENTION_RE.search(args)
    return match.group(1) if match else None


def _new_public_id(db: Session) -> str:
    while True:
        public_id = uuid.uuid4().hex[:10]
        if not db.query(ChanceGameSession.id).filter(ChanceGameSession.public_id == public_id).first():
            return public_id


def _open_game_for_user(db: Session, server_id: int, user_id: int) -> ChanceGameSession | None:
    return (
        db.query(ChanceGameSession)
        .filter(
            ChanceGameSession.server_id == server_id,
            ChanceGameSession.status.in_(("pending", "active")),
            or_(
                ChanceGameSession.challenger_id == user_id,
                ChanceGameSession.opponent_id == user_id,
            ),
        )
        .first()
    )


def _challenge(db: Session, context: PluginContext, game_type: str) -> str:
    assert context.server_id is not None and context.channel_id is not None
    mention = _extract_mention(context.args)
    if not mention:
        command = "takama" if game_type == "rps" else "yazıtura"
        return f"Kullanım: /{command} @kullanıcı"
    opponent = _find_server_user(db, context.server_id, mention)
    if not opponent:
        return f"@{mention} bu sunucuda bulunamadı."
    if opponent.id == context.user_id:
        return "Kendine oyun daveti gönderemezsin."

    current = _open_game_for_user(db, context.server_id, context.user_id)
    if current:
        return (
            f"Önce açık oyunu tamamla veya iptal et (kod: {current.public_id}). "
            f"Davetler 2, başlayan oyunlar 5 dakika içinde zaman aşımına uğrar."
        )
    opponent_game = _open_game_for_user(db, context.server_id, opponent.id)
    if opponent_game:
        return f"@{opponent.username} şu anda başka bir oyunda."

    now = _now()
    game = ChanceGameSession(
        public_id=_new_public_id(db),
        game_type=game_type,
        status="pending",
        server_id=context.server_id,
        channel_id=context.channel_id,
        challenger_id=context.user_id,
        opponent_id=opponent.id,
        expires_at=now + INVITE_TTL,
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    label = _GAME_LABELS[game_type]
    role_note = (
        "Kabul edilirse davet sahibi Yazı, rakibi Tura olur ve güvenli rastgele atış yapılır."
        if game_type == "coin"
        else "Kabulden sonra iki oyuncunun hamlesi de sonuç anına kadar gizli tutulur."
    )
    return _event(
        "invite",
        (
            f"🎮 @{context.username}, @{opponent.username} kullanıcısına {label} daveti gönderdi.\n"
            f"{role_note}\nDavet 2 dakika geçerli · kod: {game.public_id}"
        ),
        challenge_id=game.public_id,
        game=game_type,
        game_label=label,
        challenger=context.username,
        opponent=opponent.username,
        expires_at=game.expires_at.isoformat(),
    )


def _candidate_invite(
    db: Session, context: PluginContext, args: str, *, challenger_only: bool = False
) -> tuple[ChanceGameSession | None, str | None]:
    assert context.server_id is not None
    tokens = [token.strip().casefold() for token in args.split() if token.strip()]
    public_id = next((token for token in tokens if _PUBLIC_ID_RE.fullmatch(token)), None)
    game_type = next((_GAME_ALIASES[token] for token in tokens if token in _GAME_ALIASES), None)
    mention = _extract_mention(args)

    query = db.query(ChanceGameSession).filter(
        ChanceGameSession.server_id == context.server_id,
        ChanceGameSession.status == "pending",
    )
    if challenger_only:
        query = query.filter(ChanceGameSession.challenger_id == context.user_id)
    else:
        query = query.filter(ChanceGameSession.opponent_id == context.user_id)
    if public_id:
        query = query.filter(ChanceGameSession.public_id == public_id)
    if game_type:
        query = query.filter(ChanceGameSession.game_type == game_type)
    candidates = query.order_by(ChanceGameSession.created_at.desc()).all()
    if mention:
        mention_folded = mention.casefold()
        candidates = [
            game
            for game in candidates
            if game.challenger.username.casefold() == mention_folded
            or game.opponent.username.casefold() == mention_folded
        ]
    if not candidates:
        return None, "Eşleşen, süresi dolmamış bir davet bulunamadı."
    if len(candidates) > 1 and not public_id:
        codes = ", ".join(game.public_id for game in candidates[:5])
        return None, f"Birden fazla davet var. Komutta davet kodunu kullan: {codes}"
    return candidates[0], None


def _accept(db: Session, context: PluginContext) -> str:
    game, error = _candidate_invite(db, context, context.args)
    if error or game is None:
        return error or "Davet bulunamadı."
    # Kabul ve eşzamanlı süre aşımı/ret yarışında satırı kilitle.
    game = (
        db.query(ChanceGameSession)
        .filter(ChanceGameSession.id == game.id)
        .with_for_update()
        .one()
    )
    if game.status != "pending" or _has_expired(game.expires_at):
        game.status = "expired"
        game.completed_at = _now()
        db.commit()
        return _event(
            "expired",
            f"⌛ {game.public_id} kodlu davetin süresi dolmuş.",
            challenge_id=game.public_id,
            game=game.game_type,
        )

    now = _now()
    game.accepted_at = now
    if game.game_type == "coin":
        face = secrets.choice(("yazı", "tura"))
        game.challenger_move = "yazı"
        game.opponent_move = "tura"
        winner = game.challenger if face == "yazı" else game.opponent
        game.status = "completed"
        game.outcome = json.dumps({"face": face, "winner_id": winner.id}, ensure_ascii=False)
        game.completed_at = now
        db.commit()
        return _event(
            "result",
            (
                f"🪙 Para havada… Sonuç: {face.upper()}!\n"
                f"🏆 Kazanan: @{winner.username} · @{game.challenger.username}=Yazı, "
                f"@{game.opponent.username}=Tura"
            ),
            challenge_id=game.public_id,
            game="coin",
            game_label=_GAME_LABELS["coin"],
            result=face,
            winner=winner.username,
            challenger=game.challenger.username,
            opponent=game.opponent.username,
        )

    game.status = "active"
    game.expires_at = now + ACTIVE_GAME_TTL
    db.commit()
    return _event(
        "accepted",
        (
            f"⚔️ @{game.challenger.username} ile @{game.opponent.username} karşılaşması başladı!\n"
            "Komut rehberi: /taş · /kağıt · /makas\n"
            "Hamlen sohbete yazılmaz; iki oyuncu da kilitleyince sonuç birlikte açıklanır. "
            "Süre: 5 dakika."
        ),
        challenge_id=game.public_id,
        game="rps",
        game_label=_GAME_LABELS["rps"],
        challenger=game.challenger.username,
        opponent=game.opponent.username,
        expires_at=game.expires_at.isoformat(),
    )


def _reject_or_cancel(db: Session, context: PluginContext, *, cancel: bool) -> str:
    game, error = _candidate_invite(db, context, context.args, challenger_only=cancel)
    if error or game is None:
        return error or "Davet bulunamadı."
    game = db.query(ChanceGameSession).filter(ChanceGameSession.id == game.id).with_for_update().one()
    if game.status != "pending":
        return "Bu davet artık açık değil."
    game.status = "cancelled" if cancel else "rejected"
    game.completed_at = _now()
    db.commit()
    event_type = "cancelled" if cancel else "rejected"
    text = (
        f"🚫 @{game.challenger.username}, {game.public_id} kodlu daveti iptal etti."
        if cancel
        else f"🙅 @{game.opponent.username}, {game.public_id} kodlu daveti reddetti."
    )
    return _event(
        event_type,
        text,
        challenge_id=game.public_id,
        game=game.game_type,
        challenger=game.challenger.username,
        opponent=game.opponent.username,
    )


def _play_rps(db: Session, context: PluginContext, move: str) -> str:
    assert context.server_id is not None and context.channel_id is not None
    games = (
        db.query(ChanceGameSession)
        .filter(
            ChanceGameSession.server_id == context.server_id,
            ChanceGameSession.channel_id == context.channel_id,
            ChanceGameSession.game_type == "rps",
            ChanceGameSession.status == "active",
            or_(
                ChanceGameSession.challenger_id == context.user_id,
                ChanceGameSession.opponent_id == context.user_id,
            ),
        )
        .with_for_update()
        .all()
    )
    if not games:
        return "Bu kanalda aktif Taş Kağıt Makas oyunun yok. Önce /takama @kullanıcı kullan."
    if len(games) > 1:
        return "Birden fazla aktif oyun bulundu; yöneticinin oyun durumunu temizlemesi gerekiyor."
    game = games[0]
    if _has_expired(game.expires_at):
        game.status = "expired"
        game.completed_at = _now()
        db.commit()
        return _event(
            "expired",
            f"⌛ {game.public_id} kodlu oyunun süresi doldu.",
            challenge_id=game.public_id,
            game="rps",
        )

    own_field = "challenger_move" if context.user_id == game.challenger_id else "opponent_move"
    if getattr(game, own_field):
        return "Hamlen zaten kilitli. Rakibinin hamlesi bekleniyor; değiştiremezsin."
    setattr(game, own_field, move)

    if not game.challenger_move or not game.opponent_move:
        db.commit()
        waiting_for = game.opponent.username if own_field == "challenger_move" else game.challenger.username
        return _event(
            "move_locked",
            f"🔒 @{context.username} hamlesini kilitledi. @{waiting_for} bekleniyor.",
            challenge_id=game.public_id,
            game="rps",
            player=context.username,
        )

    challenger_move = game.challenger_move
    opponent_move = game.opponent_move
    if challenger_move == opponent_move:
        winner = None
        result_line = "🤝 Berabere!"
    elif (challenger_move, opponent_move) in _RPS_WINS:
        winner = game.challenger
        result_line = f"🏆 Kazanan: @{winner.username}"
    else:
        winner = game.opponent
        result_line = f"🏆 Kazanan: @{winner.username}"

    game.status = "completed"
    game.completed_at = _now()
    game.outcome = json.dumps(
        {
            "challenger_move": challenger_move,
            "opponent_move": opponent_move,
            "winner_id": winner.id if winner else None,
        },
        ensure_ascii=False,
    )
    db.commit()
    return _event(
        "result",
        (
            f"🎯 Hamleler açıldı!\n"
            f"@{game.challenger.username}: {challenger_move.upper()} · "
            f"@{game.opponent.username}: {opponent_move.upper()}\n{result_line}"
        ),
        challenge_id=game.public_id,
        game="rps",
        game_label=_GAME_LABELS["rps"],
        challenger=game.challenger.username,
        opponent=game.opponent.username,
        challenger_move=challenger_move,
        opponent_move=opponent_move,
        winner=winner.username if winner else None,
    )


def _get_wheel(db: Session, context: PluginContext, *, create: bool = False) -> ChanceWheel | None:
    assert context.server_id is not None and context.channel_id is not None
    wheel = (
        db.query(ChanceWheel)
        .filter(
            ChanceWheel.channel_id == context.channel_id,
            ChanceWheel.owner_id == context.user_id,
        )
        .first()
    )
    if not wheel and create:
        wheel = ChanceWheel(
            server_id=context.server_id,
            channel_id=context.channel_id,
            owner_id=context.user_id,
            entries=[],
        )
        db.add(wheel)
        db.flush()
    return wheel


def _parse_wheel_entry(args: str) -> tuple[str | None, int | None, str | None]:
    raw = args.strip()
    if not raw:
        return None, None, "Kullanım: /ekleçark <seçenek> veya /ekleçark <seçenek> | <ağırlık>"
    label_part, separator, weight_part = raw.rpartition("|")
    weight = 1
    label = raw
    if separator:
        label = label_part.strip()
        try:
            weight = int(weight_part.strip())
        except ValueError:
            return None, None, "Ağırlık tam sayı olmalı (1-100)."
    label = _CONTROL_RE.sub(" ", label).strip()
    if not label or len(label) > 60:
        return None, None, "Seçenek adı 1-60 karakter olmalı."
    if weight < 1 or weight > 100:
        return None, None, "Ağırlık 1-100 arasında olmalı."
    return label, weight, None


def _add_wheel_entry(db: Session, context: PluginContext) -> str:
    label, weight, error = _parse_wheel_entry(context.args)
    if error or label is None or weight is None:
        return error or "Geçersiz seçenek."
    wheel = _get_wheel(db, context, create=True)
    assert wheel is not None
    entries = list(wheel.entries or [])
    if len(entries) >= MAX_WHEEL_ENTRIES:
        return f"Çark en fazla {MAX_WHEEL_ENTRIES} seçenek alabilir."
    if any(str(entry.get("label", "")).casefold() == label.casefold() for entry in entries):
        return f"'{label}' zaten çarkta. Olasılığı artırmak için mevcut seçeneği çıkarıp ağırlıkla ekle."
    if sum(int(entry.get("weight", 1)) for entry in entries) + weight > MAX_WHEEL_WEIGHT:
        return f"Toplam çark ağırlığı {MAX_WHEEL_WEIGHT} değerini aşamaz."
    entries.append({"label": label, "weight": weight})
    wheel.entries = entries
    db.commit()
    return _event(
        "wheel_updated",
        f"🎡 '{label}' çarka eklendi (ağırlık: {weight}). Toplam {len(entries)} seçenek.",
        game="wheel",
        owner=context.username,
        entry_count=len(entries),
    )


def _list_wheel(db: Session, context: PluginContext) -> str:
    wheel = _get_wheel(db, context)
    entries = list(wheel.entries or []) if wheel else []
    if not entries:
        return "Çarkın boş. /ekleçark <seçenek> ile en az iki seçenek ekle."
    lines = [
        f"{index}. {entry['label']} (ağırlık {int(entry.get('weight', 1))})"
        for index, entry in enumerate(entries, 1)
    ]
    return "🎡 Senin çarkın:\n" + "\n".join(lines)


def _remove_wheel_entry(db: Session, context: PluginContext) -> str:
    wheel = _get_wheel(db, context)
    entries = list(wheel.entries or []) if wheel else []
    target = context.args.strip()
    if not target or not entries:
        return "Kullanım: /çıkarçark <sıra-numarası|seçenek-adı>"
    remove_index: int | None = None
    if target.isdigit() and 1 <= int(target) <= len(entries):
        remove_index = int(target) - 1
    else:
        folded = target.casefold()
        remove_index = next(
            (index for index, entry in enumerate(entries) if str(entry.get("label", "")).casefold() == folded),
            None,
        )
    if remove_index is None:
        return f"'{target}' çarkta bulunamadı. /çarkliste ile seçenekleri gör."
    removed = entries.pop(remove_index)
    wheel.entries = entries
    db.commit()
    return _event(
        "wheel_updated",
        f"🎡 '{removed['label']}' çarktan çıkarıldı. {len(entries)} seçenek kaldı.",
        game="wheel",
        owner=context.username,
        entry_count=len(entries),
    )


def _clear_wheel(db: Session, context: PluginContext) -> str:
    wheel = _get_wheel(db, context)
    if not wheel or not wheel.entries:
        return "Çarkın zaten boş."
    wheel.entries = []
    db.commit()
    return _event(
        "wheel_updated",
        "🧹 Çarkındaki tüm seçenekler temizlendi.",
        game="wheel",
        owner=context.username,
        entry_count=0,
    )


def _spin_wheel(db: Session, context: PluginContext) -> str:
    wheel = _get_wheel(db, context)
    entries = list(wheel.entries or []) if wheel else []
    if len(entries) < 2:
        return "Çarkı çevirmek için en az iki seçenek ekle: /ekleçark <seçenek>"
    total_weight = sum(int(entry.get("weight", 1)) for entry in entries)
    ticket = secrets.randbelow(total_weight)
    selected = entries[-1]
    cursor = 0
    for entry in entries:
        cursor += int(entry.get("weight", 1))
        if ticket < cursor:
            selected = entry
            break
    return _event(
        "wheel_result",
        f"🎡 Çark dönüyor… Sonuç: {selected['label']}!",
        game="wheel",
        owner=context.username,
        result=selected["label"],
        entry_count=len(entries),
    )


def _solo_coin(context: PluginContext) -> str:
    face = secrets.choice(("yazı", "tura"))
    return _event(
        "result",
        f"🪙 Para havada… Sonuç: {face.upper()}!",
        game="coin",
        game_label=_GAME_LABELS["coin"],
        result=face,
        winner=context.username,
    )


def handle_chance_command(db: Session, context: PluginContext) -> str:
    if context.server_id is None or context.channel_id is None:
        return "Bu komut yalnızca bir sunucu kanalında çalıştırılabilir."
    _expire_stale(db)
    command = context.command.casefold().rstrip(":")

    if command in {"şans", "sans", "oyunlar", "şans-yardım", "sans-yardim"}:
        return _event("help", _plain_help(), game="help")
    if command == "takama":
        return _challenge(db, context, "rps")
    if command in {"yazıtura", "yazitura", "yazı-tura", "yazi-tura"}:
        return _challenge(db, context, "coin") if _extract_mention(context.args) else _solo_coin(context)
    if command == "kabul":
        return _accept(db, context)
    if command == "reddet":
        return _reject_or_cancel(db, context, cancel=False)
    if command == "iptal":
        return _reject_or_cancel(db, context, cancel=True)
    if command in _RPS_COMMANDS:
        return _play_rps(db, context, _RPS_COMMANDS[command])
    if command in {"ekleçark", "eklecark"}:
        return _add_wheel_entry(db, context)
    if command in {"çarkliste", "carkliste", "çark-liste", "cark-liste"}:
        return _list_wheel(db, context)
    if command in {"çıkarçark", "cikarcark"}:
        return _remove_wheel_entry(db, context)
    if command in {"temizleçark", "temizlecark"}:
        return _clear_wheel(db, context)
    if command in {"çark", "cark"}:
        return _spin_wheel(db, context)
    return _plain_help()
