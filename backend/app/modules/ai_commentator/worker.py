from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import timedelta, timezone
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import settings
from app.core.models import User
from app.database import SessionLocal
from app.modules.ai_commentator.context_builder import build_commentary_context
from app.modules.ai_commentator.models import (
    CommentaryCooldown,
    CommentatorEvent,
    CommentatorSessionPlayer,
    GeneratedCommentary,
)
from app.modules.ai_commentator.prompt import COMMENTATOR_PROMPT_VERSION, COMMENTATOR_SYSTEM_PROMPT
from app.modules.party_lore.models import LoreEntry
from app.modules.party_lore.service import record_lore_usage
from app.platform.events import append_event
from app.platform.models import AiRun, BackgroundJob, ExperienceSession, utcnow
from app.services.ollama.client import ollama_client


class CommentaryDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shouldComment: bool
    commentary: str | None
    targetPlayerId: int | None
    tone: Literal["PLAYFUL", "DRY", "HYPE", "ANALYTICAL", "GENTLE", "DRAMATIC"] | None
    loreReferences: list[str] = Field(max_length=2)
    confidence: float = Field(ge=0, le=1)
    reasonCode: Literal[
        "NOTABLE_EVENT",
        "REPEATED_MISTAKE",
        "LORE_CALLBACK",
        "MILESTONE",
        "TEAM_MOMENT",
        "SAFETY_VETO",
        "TOO_REPETITIVE",
        "INSUFFICIENT_CONTEXT",
    ]

    @model_validator(mode="after")
    def consistent_shape(self):
        if self.shouldComment:
            if not self.commentary or not self.tone:
                raise ValueError("commentary and tone are required")
        elif self.commentary is not None or self.targetPlayerId is not None or self.tone is not None:
            raise ValueError("suppressed decisions cannot carry commentary, target or tone")
        if not self.shouldComment and self.loreReferences:
            raise ValueError("suppressed decisions cannot reference lore")
        return self


def _normalize_phrase(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _phrase_hash(value: str) -> str:
    return hashlib.sha256(_normalize_phrase(value).encode("utf-8")).hexdigest()


def _trigrams(value: str) -> set[tuple[str, str, str]]:
    words = _normalize_phrase(value).split()
    return {tuple(words[index : index + 3]) for index in range(max(0, len(words) - 2))}


def _too_similar(value: str, recent: list[str]) -> bool:
    normalized = _normalize_phrase(value)
    current = _trigrams(value)
    for prior in recent:
        if normalized == _normalize_phrase(prior):
            return True
        previous = _trigrams(prior)
        union = current | previous
        if union and len(current & previous) / len(union) >= 0.72:
            return True
    return False


def _parse_and_validate(raw: str, policy: dict[str, object]) -> tuple[CommentaryDecision, str | None]:
    try:
        payload = json.loads(raw)
        decision = CommentaryDecision.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError):
        return CommentaryDecision(
            shouldComment=False,
            commentary=None,
            targetPlayerId=None,
            tone=None,
            loreReferences=[],
            confidence=0.0,
            reasonCode="INSUFFICIENT_CONTEXT",
        ), "INVALID_MODEL_OUTPUT"

    allowed_targets = policy["allowed_target_ids"]
    allowed_lore = policy["allowed_lore_ids"]
    if decision.targetPlayerId is not None and decision.targetPlayerId not in allowed_targets:
        return decision.model_copy(
            update={
                "shouldComment": False,
                "commentary": None,
                "targetPlayerId": None,
                "tone": None,
                "loreReferences": [],
                "reasonCode": "SAFETY_VETO",
            }
        ), "TARGET_NOT_ALLOWED"
    if not set(decision.loreReferences).issubset(allowed_lore):
        return decision.model_copy(
            update={
                "shouldComment": False,
                "commentary": None,
                "targetPlayerId": None,
                "tone": None,
                "loreReferences": [],
                "reasonCode": "SAFETY_VETO",
            }
        ), "LORE_NOT_ALLOWED"
    if not decision.shouldComment:
        return decision, None

    text = decision.commentary or ""
    if len(text) > int(policy["max_chars"]):
        return decision.model_copy(
            update={
                "shouldComment": False,
                "commentary": None,
                "targetPlayerId": None,
                "tone": None,
                "loreReferences": [],
                "reasonCode": "INSUFFICIENT_CONTEXT",
            }
        ), "OUTPUT_TOO_LONG"
    if len(re.findall(r"[.!?]+(?:\s|$)", text)) > 1:
        return decision.model_copy(
            update={
                "shouldComment": False,
                "commentary": None,
                "targetPlayerId": None,
                "tone": None,
                "loreReferences": [],
                "reasonCode": "INSUFFICIENT_CONTEXT",
            }
        ), "TOO_MANY_SENTENCES"
    if any(topic and topic in text.casefold() for topic in policy["blocked_topics"]):
        return decision.model_copy(
            update={
                "shouldComment": False,
                "commentary": None,
                "targetPlayerId": None,
                "tone": None,
                "loreReferences": [],
                "reasonCode": "SAFETY_VETO",
            }
        ), "BLOCKED_TOPIC"
    if _too_similar(text, policy["recent_texts"]):
        return decision.model_copy(
            update={
                "shouldComment": False,
                "commentary": None,
                "targetPlayerId": None,
                "tone": None,
                "loreReferences": [],
                "reasonCode": "TOO_REPETITIVE",
            }
        ), "REPETITION"
    return decision, None


def _upsert_cooldown(db, *, session_id: str, scope_type: str, scope_key: str, seconds: int) -> None:
    now = utcnow()
    cooldown = (
        db.query(CommentaryCooldown)
        .filter(
            CommentaryCooldown.session_id == session_id,
            CommentaryCooldown.scope_type == scope_type,
            CommentaryCooldown.scope_key == scope_key,
        )
        .first()
    )
    if cooldown is None:
        db.add(
            CommentaryCooldown(
                session_id=session_id,
                scope_type=scope_type,
                scope_key=scope_key,
                last_used_at=now,
                cooldown_until=now + timedelta(seconds=seconds),
            )
        )
    else:
        cooldown.last_used_at = now
        cooldown.cooldown_until = now + timedelta(seconds=seconds)
        cooldown.usage_count += 1


def _store_result(
    *,
    job_id: str,
    event_id: str,
    decision: CommentaryDecision,
    suppression_code: str | None,
    response: dict,
    elapsed_ms: int,
    policy: dict[str, object],
) -> dict:
    db = SessionLocal()
    try:
        existing = (
            db.query(GeneratedCommentary)
            .filter(GeneratedCommentary.primary_event_id == event_id)
            .first()
        )
        if existing:
            return {"commentary_id": existing.id, "dispatch_state": existing.dispatch_state}
        event = db.query(CommentatorEvent).filter(CommentatorEvent.id == event_id).with_for_update().first()
        job = db.get(BackgroundJob, job_id)
        if not event or not job:
            raise ValueError("Commentator event or job disappeared")
        session = (
            db.query(ExperienceSession)
            .filter(ExperienceSession.id == event.session_id)
            .with_for_update()
            .first()
        )
        if not session:
            raise ValueError("Commentator session disappeared")

        age_seconds = (utcnow() - (event.received_at if event.received_at.tzinfo else event.received_at.replace(tzinfo=timezone.utc))).total_seconds()
        current_settings = session.settings or {}
        stale = age_seconds > max(0.5, settings.commentator_stale_seconds)
        session_blocked = session.status != "active" or bool(current_settings.get("silent_mode", False))
        deliver = decision.shouldComment and not suppression_code and not stale and not session_blocked
        dispatch_state = "delivered" if deliver else ("stale" if stale else "suppressed")
        stored_text = decision.commentary if decision.shouldComment else None
        commentary = GeneratedCommentary(
            session_id=session.id,
            primary_event_id=event.id,
            job_id=job.id,
            source_event_ids=[event.id],
            profile_key=str(current_settings.get("profile_key", "dry_sarcastic")),
            should_comment=decision.shouldComment,
            commentary_text=stored_text,
            target_player_id=decision.targetPlayerId,
            tone=decision.tone,
            lore_references=decision.loreReferences,
            confidence=decision.confidence,
            reason_code=decision.reasonCode,
            provider_model=str(response.get("model") or settings.commentator_live_model),
            input_tokens=response.get("prompt_eval_count"),
            output_tokens=response.get("eval_count"),
            latency_ms=elapsed_ms,
            phrase_hash=_phrase_hash(stored_text) if stored_text else None,
            dispatch_state=dispatch_state,
            dispatch_error_code=suppression_code or ("STALE" if stale else ("SESSION_BLOCKED" if session_blocked else None)),
            delivered_at=utcnow() if deliver else None,
        )
        db.add(commentary)
        event.processing_state = "processed"
        event.processed_at = utcnow()
        db.flush()

        db.add(
            AiRun(
                job_id=job.id,
                logical_profile="commentary-live",
                provider="ollama-gateway",
                model=commentary.provider_model or settings.commentator_live_model,
                prompt_version=COMMENTATOR_PROMPT_VERSION,
                prompt_tokens=commentary.input_tokens or 0,
                completion_tokens=commentary.output_tokens or 0,
                latency_ms=elapsed_ms,
                status="succeeded" if not suppression_code else "suppressed",
                error_code=suppression_code,
            )
        )
        if deliver:
            for lore_id in decision.loreReferences:
                entry = db.get(LoreEntry, lore_id)
                actor = db.get(User, job.actor_id) if job.actor_id else None
                if entry is not None and actor is not None:
                    record_lore_usage(
                        db,
                        entry=entry,
                        actor=actor,
                        module="ai_commentator",
                        request_id=f"commentary:{commentary.id}",
                        context={"event_id": event.id},
                    )
            intensity_seconds = {"LOW": 75, "NORMAL": 40, "HIGH": 18}.get(
                str(current_settings.get("intensity", "NORMAL")), 40
            )
            _upsert_cooldown(
                db,
                session_id=session.id,
                scope_type="GLOBAL",
                scope_key="all",
                seconds=max(12, intensity_seconds),
            )
            _upsert_cooldown(
                db,
                session_id=session.id,
                scope_type="CATEGORY",
                scope_key=event.category,
                seconds=90 if event.category in {"PLAYER_DEATH", "PLAYER_FAIL"} else 45,
            )
            if decision.targetPlayerId is not None:
                target_row = db.get(
                    CommentatorSessionPlayer,
                    {"session_id": session.id, "user_id": decision.targetPlayerId},
                )
                if target_row:
                    target_row.targeted_count += 1
                _upsert_cooldown(
                    db,
                    session_id=session.id,
                    scope_type="PLAYER",
                    scope_key=str(decision.targetPlayerId),
                    seconds=90,
                )
            session.revision += 1
            append_event(
                db,
                session,
                "commentator.commentary_generated",
                {
                    "commentary_id": commentary.id,
                    "event_id": event.id,
                    "text": commentary.commentary_text,
                    "target_player_id": commentary.target_player_id,
                    "tone": commentary.tone,
                },
                idempotency_key=f"commentary:generated:{event.id}",
            )
        db.commit()
        return {"commentary_id": commentary.id, "dispatch_state": dispatch_state}
    finally:
        db.close()


def process_commentator_job(
    job_id: str,
    *,
    chat: Callable[..., dict] = ollama_client.chat,
) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "ai_commentator" or job.job_type != "commentary.generate":
            raise ValueError("Unsupported AI Commentator job")
        event_id = str(job.input_ref.get("event_id", ""))
        event = db.get(CommentatorEvent, event_id)
        session = db.get(ExperienceSession, event.session_id) if event else None
        actor = db.get(User, job.actor_id) if job.actor_id else None
        if not event or not session or not actor:
            raise ValueError("AI Commentator job context is incomplete")
        existing = (
            db.query(GeneratedCommentary)
            .filter(GeneratedCommentary.primary_event_id == event.id)
            .first()
        )
        if existing:
            return {"commentary_id": existing.id, "dispatch_state": existing.dispatch_state}
        context, policy = build_commentary_context(db, session=session, event=event, actor=actor)
        event_id = event.id
    finally:
        db.close()

    messages = [
        {"role": "system", "content": COMMENTATOR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "INPUT_DATA_JSON:\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":")),
        },
    ]
    started = time.monotonic()
    response = chat(
        settings.commentator_live_model,
        messages,
        timeout=settings.commentator_timeout_seconds,
        options={"temperature": 0.65, "num_predict": 80},
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    message = response.get("message") if isinstance(response, dict) else None
    raw = message.get("content", "") if isinstance(message, dict) else ""
    decision, suppression_code = _parse_and_validate(str(raw), policy)
    return _store_result(
        job_id=job_id,
        event_id=event_id,
        decision=decision,
        suppression_code=suppression_code,
        response=response,
        elapsed_ms=elapsed_ms,
        policy=policy,
    )
