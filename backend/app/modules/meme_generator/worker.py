from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.core.models import User
from app.database import SessionLocal
from app.modules.meme_generator.models import (
    MemeCaptionCandidate,
    MemeGeneration,
    MemePlayerPreference,
)
from app.modules.meme_generator.prompt import MEME_PROMPT_VERSION, MEME_SYSTEM_PROMPT
from app.modules.meme_generator.safety import contains_hard_blocked_text
from app.modules.meme_generator.templates import TEMPLATES_BY_KEY
from app.modules.party_lore.service import find_entries
from app.platform.events import add_outbox_event
from app.platform.models import AiRun, BackgroundJob
from app.services.ollama.client import ollama_client


class ModelCaptionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    templateKey: str
    captions: dict[str, str]
    targetPlayerId: int | None
    loreReferences: list[str] = Field(max_length=2)
    harshness: int = Field(ge=0, le=2)
    qualityScore: float = Field(ge=0, le=1)


class ModelCaptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[ModelCaptionCandidate] = Field(min_length=3, max_length=3)


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _phrase_hash(captions: dict[str, str]) -> str:
    return hashlib.sha256(_normalized(" ".join(captions.values())).encode("utf-8")).hexdigest()


def _trigrams(value: str) -> set[tuple[str, str, str]]:
    words = _normalized(value).split()
    return {tuple(words[index : index + 3]) for index in range(max(0, len(words) - 2))}


def _too_similar(value: str, recent: list[str]) -> bool:
    current_normalized = _normalized(value)
    current = _trigrams(value)
    for prior in recent:
        if current_normalized == _normalized(prior):
            return True
        previous = _trigrams(prior)
        union = current | previous
        if union and len(current & previous) / len(union) >= 0.72:
            return True
    return False


def _build_context(db, generation: MemeGeneration, actor: User) -> tuple[dict, dict]:
    event = generation.event_snapshot
    participant_ids = sorted(set(event.get("actor_player_ids", [])) | set(event.get("target_player_ids", [])))
    preferences = {
        user_id: db.get(MemePlayerPreference, {"server_id": generation.server_id, "user_id": user_id})
        for user_id in participant_ids
    }
    allowed_targets = [
        user_id
        for user_id in (event.get("target_player_ids") or event.get("actor_player_ids") or [])
        if preferences.get(user_id) is None or preferences[user_id].allow_as_target
    ]
    allow_lore = all(
        preference is None or preference.allow_lore_references
        for preference in preferences.values()
    )
    lore_entries = []
    if allow_lore:
        lore_entries = find_entries(
            db,
            server_id=generation.server_id,
            actor=actor,
            module="meme_generator",
            query=str(event.get("summary", "")),
            participant_ids=participant_ids,
            limit=2,
        )
    user_rows = db.query(User).filter(User.id.in_(participant_ids)).all() if participant_ids else []
    players = [
        {"id": user.id, "displayName": user.display_name or user.username}
        for user in user_rows
    ]
    templates = []
    for key in generation.eligible_template_keys:
        template = TEMPLATES_BY_KEY[key]
        templates.append(
            {
                "key": key,
                "name": template.name,
                "zones": [
                    {"key": zone.key, "maxChars": zone.max_chars, "maxLines": zone.max_lines}
                    for zone in template.zones
                ],
            }
        )
    recent_rows = (
        db.query(MemeCaptionCandidate)
        .join(MemeGeneration, MemeGeneration.id == MemeCaptionCandidate.generation_id)
        .filter(MemeGeneration.server_id == generation.server_id)
        .order_by(MemeCaptionCandidate.created_at.desc())
        .limit(30)
        .all()
    )
    blocked_topics = sorted(
        {
            topic
            for preference in preferences.values()
            if preference is not None
            for topic in preference.blocked_topics
        }
    )
    context = {
        "language": "tr-TR",
        "event": event,
        "category": generation.category,
        "players": players,
        "templates": templates,
        "lore": [
            {"id": entry.id, "title": entry.title, "summary": entry.summary}
            for entry in lore_entries
        ],
        "allowedTemplateKeys": generation.eligible_template_keys,
        "allowedTargetPlayerIds": allowed_targets,
        "allowedLoreIds": [entry.id for entry in lore_entries],
        "maximumHarshness": generation.desired_harshness,
        "blockedTopics": blocked_topics,
        "recentCaptions": [row.captions for row in recent_rows[:10]],
    }
    policy = {
        "allowed_targets": set(allowed_targets),
        "allowed_lore": {entry.id for entry in lore_entries},
        "allowed_templates": set(generation.eligible_template_keys),
        "blocked_topics": blocked_topics,
        "recent_texts": [" ".join(row.captions.values()) for row in recent_rows],
        "maximum_harshness": generation.desired_harshness,
    }
    return context, policy


def _validate_response(raw: str, policy: dict) -> list[ModelCaptionCandidate]:
    try:
        parsed = ModelCaptionResponse.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ValueError("INVALID_MODEL_OUTPUT") from exc
    accepted: list[ModelCaptionCandidate] = []
    seen_phrases: list[str] = []
    for candidate in parsed.candidates:
        if candidate.templateKey not in policy["allowed_templates"]:
            raise ValueError("TEMPLATE_NOT_ALLOWED")
        if candidate.targetPlayerId is not None and candidate.targetPlayerId not in policy["allowed_targets"]:
            raise ValueError("TARGET_NOT_ALLOWED")
        if not set(candidate.loreReferences).issubset(policy["allowed_lore"]):
            raise ValueError("LORE_NOT_ALLOWED")
        if candidate.harshness > policy["maximum_harshness"]:
            raise ValueError("HARSHNESS_NOT_ALLOWED")
        template = TEMPLATES_BY_KEY[candidate.templateKey]
        zone_keys = {zone.key for zone in template.zones}
        if set(candidate.captions) != zone_keys:
            raise ValueError("CAPTION_ZONE_MISMATCH")
        for zone in template.zones:
            text = " ".join(str(candidate.captions[zone.key]).split())
            if not text or len(text) > zone.max_chars:
                raise ValueError("CAPTION_TOO_LONG")
            candidate.captions[zone.key] = text
        combined = " ".join(candidate.captions.values())
        if len(combined.split()) > 18:
            raise ValueError("CAPTION_TOO_MANY_WORDS")
        if any(topic and topic in combined.casefold() for topic in policy["blocked_topics"]):
            raise ValueError("BLOCKED_TOPIC")
        if contains_hard_blocked_text(combined):
            raise ValueError("SAFETY_VETO")
        if _too_similar(combined, policy["recent_texts"] + seen_phrases):
            raise ValueError("REPETITIVE_CAPTION")
        if candidate.qualityScore < 0.55:
            raise ValueError("LOW_QUALITY")
        seen_phrases.append(combined)
        accepted.append(candidate)
    return accepted


def _store_failure(job_id: str, generation_id: str, error_code: str, response: dict, elapsed_ms: int) -> dict:
    db = SessionLocal()
    try:
        generation = db.get(MemeGeneration, generation_id)
        if generation:
            generation.status = "failed"
            generation.error_code = error_code
        db.add(
            AiRun(
                job_id=job_id,
                logical_profile="meme-text",
                provider="ollama-gateway",
                model=str(response.get("model") or settings.meme_text_model),
                prompt_version=MEME_PROMPT_VERSION,
                prompt_tokens=int(response.get("prompt_eval_count") or 0),
                completion_tokens=int(response.get("eval_count") or 0),
                latency_ms=elapsed_ms,
                status="suppressed",
                error_code=error_code,
            )
        )
        db.commit()
        return {"generation_id": generation_id, "status": "failed", "error_code": error_code}
    finally:
        db.close()


def process_meme_job(job_id: str, *, chat: Callable[..., dict] = ollama_client.chat) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "meme_generator" or job.job_type != "meme.caption":
            raise ValueError("Unsupported Meme Generator job")
        generation_id = str(job.input_ref.get("generation_id", ""))
        generation = db.get(MemeGeneration, generation_id)
        actor = db.get(User, job.actor_id) if job.actor_id else None
        if not generation or not actor:
            raise ValueError("Meme Generator job context is incomplete")
        if generation.candidates:
            return {"generation_id": generation.id, "status": "candidates_ready"}
        generation.status = "generating"
        db.commit()
        context, policy = _build_context(db, generation, actor)
    finally:
        db.close()

    started = time.monotonic()
    response = chat(
        settings.meme_text_model,
        [
            {"role": "system", "content": MEME_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "INPUT_DATA_JSON:\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            },
        ],
        timeout=settings.meme_timeout_seconds,
        options={"temperature": 0.72, "num_predict": 360},
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    message = response.get("message") if isinstance(response, dict) else None
    raw = message.get("content", "") if isinstance(message, dict) else ""
    try:
        candidates = _validate_response(str(raw), policy)
    except ValueError as exc:
        return _store_failure(job_id, generation_id, str(exc), response, elapsed_ms)

    db = SessionLocal()
    try:
        generation = db.get(MemeGeneration, generation_id)
        if not generation:
            raise ValueError("Meme generation disappeared")
        if generation.candidates:
            return {"generation_id": generation.id, "status": "candidates_ready"}
        for rank, candidate in enumerate(candidates, start=1):
            template = TEMPLATES_BY_KEY[candidate.templateKey]
            db.add(
                MemeCaptionCandidate(
                    generation_id=generation.id,
                    rank=rank,
                    template_key=template.key,
                    template_version=template.version,
                    category=generation.category or "CURSED_PLAN",
                    captions=candidate.captions,
                    target_player_id=candidate.targetPlayerId,
                    lore_references=candidate.loreReferences,
                    harshness=candidate.harshness,
                    quality_score=candidate.qualityScore,
                    phrase_hash=_phrase_hash(candidate.captions),
                )
            )
        generation.status = "candidates_ready"
        generation.error_code = None
        db.add(
            AiRun(
                job_id=job_id,
                logical_profile="meme-text",
                provider="ollama-gateway",
                model=str(response.get("model") or settings.meme_text_model),
                prompt_version=MEME_PROMPT_VERSION,
                prompt_tokens=int(response.get("prompt_eval_count") or 0),
                completion_tokens=int(response.get("eval_count") or 0),
                latency_ms=elapsed_ms,
                status="succeeded",
            )
        )
        add_outbox_event(
            db,
            topic="meme_generator.events",
            aggregate_type="meme_generation",
            aggregate_id=generation.id,
            event_type="meme.candidates_ready",
            payload={"generation_id": generation.id, "candidate_count": 3},
        )
        db.commit()
        return {"generation_id": generation.id, "status": "candidates_ready"}
    finally:
        db.close()
