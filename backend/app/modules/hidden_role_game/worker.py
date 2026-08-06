from __future__ import annotations

import json
import time
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.database import SessionLocal
from app.platform.events import append_event
from app.platform.models import AiRun, BackgroundJob, ExperienceEvent, ExperienceSession
from app.services.ollama.client import ollama_client


class RecapOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recap: str = Field(min_length=1, max_length=700)


def process_hidden_recap_job(job_id: str, *, chat: Callable[..., dict] = ollama_client.chat) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id); event = db.get(ExperienceEvent, int(job.input_ref["event_id"])) if job else None
        if not job or job.module != "hidden_role_game" or job.job_type != "hidden.end_recap" or not event or event.event_type != "hidden.roles_revealed": raise ValueError("Unsupported hidden-role recap job")
        payload = event.public_payload
    finally: db.close()
    prompt = "Yalnız açıklanmış sonucu kullanan nazik Türkçe oyun sonu anlatıcısısın. Kazananı veya puanı değiştirme. JSON: {\"recap\":\"en çok 120 kelime\"}."
    started = time.monotonic(); response = chat(settings.hidden_role_recap_model, [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], timeout=settings.hidden_role_recap_timeout_seconds, options={"temperature": .35, "num_predict": 240})
    try: output = RecapOutput.model_validate(json.loads(response["message"]["content"]))
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc: raise ValueError("INVALID_HIDDEN_RECAP") from exc
    db = SessionLocal()
    try:
        event = db.get(ExperienceEvent, int(job.input_ref["event_id"])); session = db.get(ExperienceSession, event.session_id)
        append_event(db, session, "hidden.recap_ready", {"source_event_id": event.id, "text": output.recap}, idempotency_key=f"hidden:recap:{event.id}")
        db.add(AiRun(job_id=job_id, logical_profile="hidden_role_end_narrator", provider="ollama-gateway", model=str(response.get("model") or settings.hidden_role_recap_model), prompt_version="hidden-end-v1", latency_ms=int((time.monotonic()-started)*1000), status="succeeded")); db.commit()
        return {"recap": output.recap}
    finally: db.close()
