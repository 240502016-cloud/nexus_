from __future__ import annotations

import json
import time
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.core.models import User
from app.database import SessionLocal
from app.modules.party_lore.service import find_entries, record_lore_usage
from app.platform.events import append_event
from app.platform.models import AiRun, BackgroundJob, ExperienceEvent, ExperienceSession
from app.services.ollama.client import ollama_client


class StoryText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=1400)


def process_story_job(job_id: str, *, chat: Callable[..., dict] = ollama_client.chat) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "shared_story" or job.job_type not in {"story.scene_write", "story.ending_write"}: raise ValueError("Unsupported story job")
        event = db.get(ExperienceEvent, int(job.input_ref["event_id"])); session = db.get(ExperienceSession, event.session_id) if event else None; actor = db.get(User, job.actor_id) if job.actor_id else None
        if not event or not session: raise ValueError("Story source missing")
        context = {"kind": job.input_ref.get("content_kind"), "committed_event": event.public_payload, "theme": (session.settings or {}).get("theme"), "safety_envelope": event.public_payload.get("safety_envelope")}
        lore = None
        if actor and (session.settings or {}).get("use_party_lore"):
            entries = find_entries(db, server_id=session.server_id, actor=actor, module="shared_story", participant_ids=[player.user_id for player in session.players], limit=1)
            if entries: lore = entries[0]; context["fictional_distance_flavor"] = {"title": lore.title, "summary": lore.summary[:220], "instruction": "Adı, bağlamı ve sonucu değiştir; mekanik gerçek veya kişisel şaka yapma."}
    finally: db.close()
    system = """Üç Yol, Tek Kader için Türkçe sahne yazarısın. Yalnız commit edilmiş sonucu anlat; mekanik, sonuç, seçim, eşya veya sır ekleme. Güvenlik zarfını aşma. Lore varsa kurmaca mesafesiyle yalnız dekoratif esinti yap. JSON {\"text\":\"...\"}. Açılış en çok 300, sahne 140, final 350 kelime."""
    started = time.monotonic(); response = chat(settings.shared_story_model, [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(context, ensure_ascii=False)}], timeout=settings.shared_story_timeout_seconds, options={"temperature": .65, "num_predict": 650})
    try: output = StoryText.model_validate(json.loads(response["message"]["content"]))
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc: raise ValueError("INVALID_STORY_OUTPUT") from exc
    db = SessionLocal()
    try:
        event = db.get(ExperienceEvent, int(job.input_ref["event_id"])); session = db.get(ExperienceSession, event.session_id); actor = db.get(User, job.actor_id) if job.actor_id else None
        append_event(db, session, "story.prose_ready", {"source_event_id": event.id, "content_kind": job.input_ref.get("content_kind"), "text": output.text, "lore_reference_ids": [lore.id] if lore else []}, idempotency_key=f"story:prose-ready:{event.id}")
        if lore and actor: record_lore_usage(db, entry=lore, actor=actor, module="shared_story", request_id=f"story:{event.id}", context={"content_kind": job.input_ref.get("content_kind")})
        db.add(AiRun(job_id=job_id, logical_profile="shared_story_ending_writer" if job.job_type == "story.ending_write" else "shared_story_scene_writer", provider="ollama-gateway", model=str(response.get("model") or settings.shared_story_model), prompt_version="shared-story-v1", latency_ms=int((time.monotonic()-started)*1000), status="succeeded")); db.commit(); return {"text": output.text}
    finally: db.close()
