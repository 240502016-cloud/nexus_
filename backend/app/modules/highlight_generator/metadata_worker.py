from __future__ import annotations

import json
import time
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.database import SessionLocal
from app.modules.highlight_generator.models import HighlightCandidate, HighlightMarker
from app.platform.events import add_outbox_event
from app.platform.models import AiRun, BackgroundJob
from app.services.ollama.client import ollama_client


PROMPT_VERSION = "highlight-metadata-v1"
SYSTEM_PROMPT = """Sen Nexus Highlight Generator metadata yazıcısısın.
Yalnız INPUT_DATA_JSON içindeki doğrulanmış marker özetini kullan. Yeni oyuncu, olay, sayı, alıntı veya niyet
uydurma. Başlık en fazla 120, açıklama en fazla 300 karakter Türkçe olsun. Kişiyi aşağılayan etiket, küfür,
özel hayat, korunan özellik veya oyun dışı iddia kullanma. Açıklama veya markdown eklemeden yalnız JSON döndür:
{"title":"...","description":"...","memeCandidate":false,"loreCandidate":false}
"""


class MetadataDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=300)
    memeCandidate: bool
    loreCandidate: bool


def process_highlight_metadata_job(
    job_id: str,
    *,
    chat: Callable[..., dict] = ollama_client.chat,
) -> dict:
    db = SessionLocal()
    try:
        job = db.get(BackgroundJob, job_id)
        if not job or job.module != "highlight_generator" or job.job_type != "highlight.metadata":
            raise ValueError("Unsupported highlight metadata job")
        candidate_id = str(job.input_ref.get("candidate_id", ""))
        candidate = db.get(HighlightCandidate, candidate_id)
        marker = db.get(HighlightMarker, candidate.marker_id) if candidate else None
        if not candidate or not marker:
            raise ValueError("Highlight metadata context is incomplete")
        context = {
            "category": candidate.primary_category,
            "summary": marker.summary,
            "participants": marker.participant_player_ids,
            "startMs": candidate.start_ms,
            "endMs": candidate.end_ms,
            "allowedFacts": [marker.summary] if marker.summary else [],
        }
    finally:
        db.close()

    started = time.monotonic()
    response = chat(
        settings.highlight_metadata_model,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "INPUT_DATA_JSON:\n" + json.dumps(context, ensure_ascii=False)},
        ],
        timeout=settings.highlight_metadata_timeout_seconds,
        options={"temperature": 0.35, "num_predict": 150},
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    message = response.get("message") if isinstance(response, dict) else None
    raw = message.get("content", "") if isinstance(message, dict) else ""
    try:
        decision = MetadataDecision.model_validate(json.loads(str(raw)))
    except (json.JSONDecodeError, ValidationError, TypeError):
        decision = None

    db = SessionLocal()
    try:
        candidate = db.get(HighlightCandidate, candidate_id)
        status = "succeeded" if decision else "suppressed"
        error_code = None if decision else "INVALID_MODEL_OUTPUT"
        if decision and candidate.status == "proposed":
            candidate.title = " ".join(decision.title.split())
            candidate.description = " ".join(decision.description.split())
            candidate.meme_candidate = candidate.meme_candidate and decision.memeCandidate
            candidate.lore_candidate = candidate.lore_candidate and decision.loreCandidate
            add_outbox_event(
                db,
                topic="highlight_generator.events",
                aggregate_type="highlight_candidate",
                aggregate_id=candidate.id,
                event_type="highlight.metadata_ready",
                payload={"candidate_id": candidate.id},
            )
        db.add(
            AiRun(
                job_id=job_id,
                logical_profile="highlight-metadata",
                provider="ollama-gateway",
                model=str(response.get("model") or settings.highlight_metadata_model),
                prompt_version=PROMPT_VERSION,
                prompt_tokens=int(response.get("prompt_eval_count") or 0),
                completion_tokens=int(response.get("eval_count") or 0),
                latency_ms=elapsed_ms,
                status=status,
                error_code=error_code,
            )
        )
        db.commit()
        return {"candidate_id": candidate_id, "status": status, "error_code": error_code}
    finally:
        db.close()

