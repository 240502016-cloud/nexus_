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
from app.modules.ai_roast_battle.models import RoastCandidate, RoastRound, RoastSessionPlayer
from app.modules.meme_generator.safety import contains_hard_blocked_text
from app.modules.party_lore.models import LoreEntry
from app.modules.party_lore.service import record_lore_usage
from app.platform.events import append_event
from app.platform.models import AiRun, BackgroundJob, ExperienceSession, utcnow
from app.services.ollama.client import ollama_client


GEN_PROMPT_VERSION = "roast-generate-v1"
REVIEW_PROMPT_VERSION = "roast-review-v1"
GEN_SYSTEM = """Yalnız verilen doğrulanmış oyun olayını kullanan güvenli Türkçe roast yazarı ol.
Kişiliği değil oyun anını hedefle. Gerçek hayat, sağlık, görünüş, kimlik, aile, iş, para, travma, ilişki,
özel mesaj, tehdit, küfür ve kalıcı aşağılayıcı etiket kullanma. Yeni olay/sayı/alıntı uydurma.
Tam üç farklı aday ve yalnız JSON döndür: {"candidates":[{"text":"...","angle":"BAD_TIMING","intensity":1,"confidence":0.9,"qualityScore":0.8}]}"""
REVIEW_SYSTEM = """Bağımsız güvenlik denetçisisin. Her adayın yalnız verilen oyun kanıtına dayandığını ve
gerçek kişiyi aşağılamadığını kontrol et. En iyi güvenli adayın sıfır tabanlı indeksini seç. Hiçbiri güvenli
değilse allowed=false döndür. Yalnız JSON: {"allowed":true,"selectedIndex":0,"riskFlags":[]}"""


class GeneratedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=280)
    angle: str = Field(min_length=1, max_length=40)
    intensity: int = Field(ge=0, le=2)
    confidence: float = Field(ge=0, le=1)
    qualityScore: float = Field(ge=0, le=1)


class GeneratedSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[GeneratedItem] = Field(min_length=3, max_length=3)


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: bool
    selectedIndex: int | None = Field(default=None, ge=0, le=2)
    riskFlags: list[str] = Field(max_length=10)


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def process_roast_job(job_id: str, *, chat: Callable[..., dict] = ollama_client.chat) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "ai_roast_battle" or job.job_type != "roast.generate_review":
            raise ValueError("Unsupported roast job")
        round_id = str(job.input_ref.get("round_id", ""))
        round_row = db.get(RoastRound, round_id)
        session = db.get(ExperienceSession, round_row.session_id) if round_row else None
        target = db.get(User, round_row.target_player_id) if round_row else None
        session_player = db.get(RoastSessionPlayer, {"session_id": session.id, "user_id": target.id}) if session and target else None
        if not round_row or not session or not target or not session_player or session.status != "active" or session_player.consent_state != "ready":
            raise ValueError("Roast consent fence failed")
        existing = db.query(RoastCandidate).filter_by(round_id=round_row.id).first()
        if existing:
            return {"round_id": round_row.id, "candidate_id": existing.id}
        policy = {"maximumIntensity": round_row.effective_intensity, "blockedTerms": session_player.profile_snapshot.get("blocked_terms", [])}
        context = {"target": {"id": target.id, "displayName": target.display_name or target.username}, "source": round_row.source_snapshot, "policy": policy}
    finally:
        db.close()

    started = time.monotonic()
    generate_response = chat(settings.roast_generate_model, [{"role": "system", "content": GEN_SYSTEM}, {"role": "user", "content": "INPUT_DATA_JSON:\n" + json.dumps(context, ensure_ascii=False)}], timeout=settings.roast_generate_timeout_seconds, options={"temperature": 0.72, "num_predict": 260})
    generate_ms = int((time.monotonic() - started) * 1000)
    raw = (generate_response.get("message") or {}).get("content", "")
    try:
        generated = GeneratedSet.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ValueError("INVALID_GENERATION_OUTPUT") from exc
    recent_hashes = set()
    db = SessionLocal()
    try:
        recent_hashes = {row[0] for row in db.query(RoastCandidate.phrase_hash).limit(100).all()}
    finally:
        db.close()
    for item in generated.candidates:
        normalized = _normalized(item.text)
        if item.intensity > policy["maximumIntensity"] or contains_hard_blocked_text(item.text) or any(term and term in item.text.casefold() for term in policy["blockedTerms"]):
            raise ValueError("DETERMINISTIC_SAFETY_VETO")
        if hashlib.sha256(normalized.encode()).hexdigest() in recent_hashes:
            raise ValueError("REPETITIVE_ROAST")

    review_started = time.monotonic()
    review_response = chat(settings.roast_review_model, [{"role": "system", "content": REVIEW_SYSTEM}, {"role": "user", "content": json.dumps({"source": context["source"], "candidates": [item.model_dump() for item in generated.candidates]}, ensure_ascii=False)}], timeout=settings.roast_review_timeout_seconds, options={"temperature": 0.0, "num_predict": 80})
    review_ms = int((time.monotonic() - review_started) * 1000)
    try:
        review = ReviewDecision.model_validate(json.loads((review_response.get("message") or {}).get("content", "")))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ValueError("INVALID_REVIEW_OUTPUT") from exc
    if not review.allowed or review.selectedIndex is None:
        raise ValueError("NO_SAFE_ROAST")
    selected = generated.candidates[review.selectedIndex]

    db = SessionLocal()
    try:
        round_row = db.get(RoastRound, round_id)
        session = db.get(ExperienceSession, round_row.session_id)
        session_player = db.get(RoastSessionPlayer, {"session_id": session.id, "user_id": round_row.target_player_id})
        if session.status != "active" or session_player.consent_state != "ready":
            raise ValueError("Roast consent revoked before delivery")
        phrase_hash = hashlib.sha256(_normalized(selected.text).encode()).hexdigest()
        candidate = RoastCandidate(round_id=round_row.id, target_player_id=round_row.target_player_id, roast_text=selected.text, phrase_hash=phrase_hash, angle=selected.angle, intensity=selected.intensity, source_lore_ids=[round_row.source_snapshot["id"]] if round_row.source_snapshot.get("type") == "PARTY_LORE" else [], confidence=selected.confidence, quality_score=selected.qualityScore)
        db.add(candidate)
        db.flush()
        round_row.selected_candidate_id = candidate.id
        round_row.status = "voting"
        session.revision += 1
        append_event(db, session, "roast.candidate_displayed", {"round_id": round_row.id, "candidate_id": candidate.id, "target_player_id": candidate.target_player_id, "text": candidate.roast_text}, idempotency_key=f"roast:display:{round_row.id}")
        if candidate.source_lore_ids:
            entry = db.get(LoreEntry, candidate.source_lore_ids[0])
            actor = db.get(User, job.actor_id)
            if entry and actor:
                record_lore_usage(db, entry=entry, actor=actor, module="ai_roast_battle", request_id=f"roast:{candidate.id}", context={"round_id": round_row.id})
        db.add_all([
            AiRun(job_id=job_id, logical_profile="roast-generate", provider="ollama-gateway", model=str(generate_response.get("model") or settings.roast_generate_model), prompt_version=GEN_PROMPT_VERSION, latency_ms=generate_ms, status="succeeded"),
            AiRun(job_id=job_id, logical_profile="roast-review", provider="ollama-gateway", model=str(review_response.get("model") or settings.roast_review_model), prompt_version=REVIEW_PROMPT_VERSION, latency_ms=review_ms, status="succeeded"),
        ])
        db.commit()
        return {"round_id": round_row.id, "candidate_id": candidate.id}
    finally:
        db.close()

