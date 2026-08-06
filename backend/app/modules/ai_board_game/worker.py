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


PROMPT_VERSION = "board-narrator-v1"
SYSTEM_PROMPT = """Son Portal için kısa bir Türkçe oyun anlatıcısısın. Yalnız verilen mekanik özeti süsle.
Yeni sonuç, sayı, eşya, oyuncu hedefi veya kural uydurma. Tek cümle ve en çok 220 karakter yaz.
Yalnız JSON döndür: {\"narration\":\"...\"}."""


class NarrationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narration: str = Field(min_length=1, max_length=220)


def process_board_narration_job(job_id: str, *, chat: Callable[..., dict] = ollama_client.chat) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "ai_board_game" or job.job_type != "board.narrate":
            raise ValueError("Unsupported board narration job")
        event = db.get(ExperienceEvent, int(job.input_ref["event_id"]))
        session = db.get(ExperienceSession, event.session_id) if event else None
        if not event or not session or event.event_type != "board.action_resolved":
            raise ValueError("Board narration source is missing")
        payload = {"mechanical_summary": event.public_payload.get("mechanical_summary"), "kind": event.public_payload.get("kind"), "round": event.public_payload.get("round")}
    finally:
        db.close()
    started = time.monotonic()
    response = chat(settings.board_game_narrator_model, [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], timeout=settings.board_game_narrator_timeout_seconds, options={"temperature": 0.45, "num_predict": 100})
    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        output = NarrationOutput.model_validate(json.loads(response["message"]["content"]))
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("INVALID_BOARD_NARRATION") from exc
    db = SessionLocal()
    try:
        event = db.get(ExperienceEvent, int(job.input_ref["event_id"]))
        session = db.get(ExperienceSession, event.session_id)
        append_event(db, session, "board.narration_ready", {"source_event_id": event.id, "text": output.narration, "fallback_used": False}, idempotency_key=f"board:narration:{event.id}")
        db.add(AiRun(job_id=job_id, logical_profile="board_game_narrator", provider="ollama-gateway", model=str(response.get("model") or settings.board_game_narrator_model), prompt_version=PROMPT_VERSION, latency_ms=latency_ms, status="succeeded"))
        db.commit()
        return {"event_id": event.id, "narration": output.narration}
    finally:
        db.close()
