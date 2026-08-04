"""Token sayımı ve kullanım takibi.

Ollama, /api/chat yanıtında modelin kendi gerçek tokenizer'ıyla saydığı
prompt_eval_count (girdi) ve eval_count (çıktı) değerlerini döner. Bu yüzden ayrı,
tahmini bir tokenizer kütüphanesi (tiktoken vb.) kullanmıyoruz - farklı modellerin
farklı tokenizer'ları olduğu için tahmin gerçek sayıyla örtüşmez; kaynağından okumak
her zaman doğrudur.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.ollama.models import AiTokenUsage


def estimate_tokens(text: str) -> int:
    """Conservative model-agnostic estimate used before Ollama returns real token counts.

    Different local models have different tokenizers, so this is intentionally an estimate
    (roughly four Unicode characters per token), not a billing number. Real usage is still
    recorded from Ollama's prompt_eval_count/eval_count response fields.
    """
    return max(1, ceil(len(text) / 4))


def estimate_message_tokens(message: dict) -> int:
    return 4 + estimate_tokens(str(message.get("content", "")))


_TRUNCATION_MARKER = "\n…[önceki bağlam kısaltıldı]…\n"


def _truncate_message(message: dict, max_content_chars: int) -> dict:
    """Return a bounded copy while preserving instructions at the head and recency at the tail."""
    content = str(message.get("content", ""))
    if len(content) <= max_content_chars:
        return message
    if max_content_chars <= len(_TRUNCATION_MARKER):
        shortened = content[-max_content_chars:]
    else:
        usable = max_content_chars - len(_TRUNCATION_MARKER)
        head_size = usable // 3
        tail_size = usable - head_size
        shortened = f"{content[:head_size]}{_TRUNCATION_MARKER}{content[-tail_size:]}"
    return {**message, "content": shortened}


def build_token_limited_context(
    history: list[dict], *, system_prompt: str, token_budget: int
) -> list[dict]:
    """Keep the newest complete messages that fit the prompt token budget."""
    system = {"role": "system", "content": system_prompt}
    used = estimate_message_tokens(system)
    # Güvenlik/davranış talimatı hiçbir koşulda budanmaz; en az bir kısa kullanıcı mesajı
    # için de yer ayrılır. Normal yapılandırmada bu yalnızca verilen token bütçesidir.
    budget = max(128, token_budget, used + 5)
    selected: list[dict] = []
    for message in reversed(history):
        cost = estimate_message_tokens(message)
        remaining = budget - used
        if cost <= remaining:
            selected.append(message)
            used += cost
            continue
        if selected:
            break
        # En yeni mesaj tek başına bütçeyi aşıyorsa eski davranış tüm içeriği göndererek
        # limiti fiilen devre dışı bırakıyordu. Baş ve sonu korumak, talimatı ve en güncel
        # dökümü kaybetmeden ağ/token/RAM kullanımını gerçekten sınırlar.
        content_token_budget = max(1, remaining - 4)
        selected.append(_truncate_message(message, content_token_budget * 4))
        break
    selected.reverse()
    return [system, *selected]


@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @classmethod
    def from_ollama_response(cls, response: dict) -> "TokenUsage":
        return cls(
            prompt_tokens=response.get("prompt_eval_count", 0) or 0,
            completion_tokens=response.get("eval_count", 0) or 0,
        )


def record_usage(db: Session, *, user_id: int, conversation_id: int, model: str, usage: TokenUsage) -> None:
    db.add(
        AiTokenUsage(
            user_id=user_id,
            conversation_id=conversation_id,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
        )
    )


def usage_summary_for_user(db: Session, user_id: int) -> list[dict]:
    """Kullanıcının modele göre gruplanmış toplam token kullanımı."""
    rows = (
        db.query(
            AiTokenUsage.model,
            func.sum(AiTokenUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(AiTokenUsage.completion_tokens).label("completion_tokens"),
        )
        .filter(AiTokenUsage.user_id == user_id)
        .group_by(AiTokenUsage.model)
        .all()
    )
    return [
        {
            "model": row.model,
            "prompt_tokens": int(row.prompt_tokens or 0),
            "completion_tokens": int(row.completion_tokens or 0),
            "total_tokens": int((row.prompt_tokens or 0) + (row.completion_tokens or 0)),
        }
        for row in rows
    ]
