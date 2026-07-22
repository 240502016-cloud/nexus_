"""AI (Ollama) sohbet uç noktaları - model seçimi, sohbet geçmişi/context yönetimi,
token kullanım takibi.

Not: bu dosyanın adı `requests.py` (spec'teki services/ollama/requests yapısına göre);
üçüncü parti `requests` HTTP kütüphanesiyle çakışmaz çünkü bu modül her zaman
`app.services.ollama.requests` tam yoluyla içe aktarılır, asla çıplak `requests` olarak
değil - Python'ın mutlak import çözümlemesi (PEP 328) bunu garanti eder.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_user
from app.core.models import User
from app.database import SessionLocal, get_db
from app.services.ollama.client import (
    OllamaError,
    OllamaGatewayAuthenticationError,
    OllamaGatewayTimeoutError,
    OllamaGatewayUnavailableError,
    OllamaModelNotFoundError,
    ollama_client,
)
from app.services.ollama.models import (
    AiConversation,
    AiJob,
    AiJobRead,
    AiJobStatus,
    AiMessage,
    ConversationCreate,
    ConversationRead,
    GatewayHealth,
    MessageCreate,
    MessageRead,
    MessageRole,
    ModelInfo,
    UsageSummary,
    utcnow,
)
from app.services.ollama.tokenizer import usage_summary_for_user

router = APIRouter(prefix="/ai", tags=["ai"])


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _ollama_http_exception(exc: OllamaError) -> HTTPException:
    if isinstance(exc, OllamaModelNotFoundError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, OllamaGatewayTimeoutError):
        return HTTPException(status_code=504, detail=str(exc))
    if isinstance(exc, OllamaGatewayUnavailableError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, OllamaGatewayAuthenticationError):
        # Gateway credential hatası sunucu yapılandırma problemidir; kullanıcı auth hatası değildir.
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/health", response_model=GatewayHealth)
def gateway_health(current_user: User = Depends(get_current_user)):
    try:
        return ollama_client.health(force_refresh=True)
    except OllamaError as exc:
        raise _ollama_http_exception(exc) from exc


@router.get("/models", response_model=list[ModelInfo])
def list_models(current_user: User = Depends(get_current_user)):
    try:
        models = ollama_client.list_models()
    except OllamaError as exc:
        raise _ollama_http_exception(exc) from exc
    return [ModelInfo(name=m["name"], size=m.get("size")) for m in models]


@router.post("/conversations", response_model=ConversationRead, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = (payload.model or settings.ollama_default_model).strip()
    try:
        ollama_client.ensure_model_available(model, force_refresh=True)
    except OllamaError as exc:
        raise _ollama_http_exception(exc) from exc

    conversation = AiConversation(
        user_id=current_user.id,
        model=model,
        title=payload.title,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(AiConversation)
        .filter(AiConversation.user_id == current_user.id)
        .order_by(AiConversation.id.desc())
        .all()
    )


def _get_owned_conversation(db: Session, conversation_id: int, user_id: int) -> AiConversation:
    conversation = db.get(AiConversation, conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_owned_conversation(db, conversation_id, current_user.id)
    return conversation.messages


@router.post("/conversations/{conversation_id}/messages", response_model=AiJobRead, status_code=202)
def send_message(
    conversation_id: int,
    payload: MessageCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_owned_conversation(db, conversation_id, current_user.id)

    stored_key = None
    if idempotency_key:
        if len(idempotency_key) > 100 or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key):
            raise HTTPException(status_code=400, detail="Idempotency-Key geçersiz")
        stored_key = f"{current_user.id}:{conversation.id}:{idempotency_key}"
        previous_job = db.query(AiJob).filter(AiJob.idempotency_key == stored_key).first()
        if previous_job:
            return previous_job

    pending_count = (
        db.query(AiJob)
        .filter(
            AiJob.user_id == current_user.id,
            AiJob.status.in_([AiJobStatus.QUEUED, AiJobStatus.RUNNING]),
        )
        .count()
    )
    if pending_count >= settings.ai_max_pending_jobs_per_user:
        raise HTTPException(
            status_code=429,
            detail="AI kuyruğunuz dolu; mevcut isteklerin tamamlanmasını bekleyin.",
        )

    user_message = AiMessage(conversation_id=conversation.id, role=MessageRole.USER, content=payload.content)
    db.add(user_message)
    db.flush()
    job = AiJob(
        conversation_id=conversation.id,
        user_id=current_user.id,
        user_message_id=user_message.id,
        idempotency_key=stored_key,
        status=AiJobStatus.QUEUED,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if stored_key:
            previous_job = db.query(AiJob).filter(AiJob.idempotency_key == stored_key).first()
            if previous_job:
                return previous_job
        raise
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}", response_model=AiJobRead)
def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(AiJob, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="AI işi bulunamadı")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=AiJobRead)
def cancel_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request cooperative cancellation of a queued or running generation."""
    job = db.execute(select(AiJob).where(AiJob.id == job_id).with_for_update()).scalar_one_or_none()
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="AI işi bulunamadı")
    if job.status in (AiJobStatus.QUEUED, AiJobStatus.RUNNING):
        job.cancel_requested = True
        if job.status == AiJobStatus.QUEUED:
            job.status = AiJobStatus.CANCELLED
            job.completed_at = utcnow()
            job.locked_by = None
            job.lease_expires_at = None
        db.commit()
        db.refresh(job)
    return job


@router.get("/jobs/{job_id}/stream")
def stream_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream durable worker output as SSE; reconnecting clients can resume from DB state."""
    job = db.get(AiJob, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="AI işi bulunamadı")
    # The long-lived SSE generator uses short-lived polling sessions instead of
    # holding FastAPI's request-scoped connection open for the whole stream.
    db.close()

    async def events():
        previous = ""
        while True:
            poll_db = None
            try:
                poll_db = SessionLocal()
                current = poll_db.get(AiJob, job_id)
                if current is None or current.user_id != current_user.id:
                    return
                output = current.output_text or ""
                status_value = current.status.value if isinstance(current.status, AiJobStatus) else str(current.status)
                if output.startswith(previous):
                    delta = output[len(previous):]
                else:
                    delta = output
                if delta:
                    yield _sse_event("token", {"job_id": job_id, "text": delta})
                    previous = output
                status_payload = {
                    "job_id": job_id,
                    "status": status_value,
                    "output_text": output,
                    "error": current.error,
                    "cancel_requested": bool(current.cancel_requested),
                }
                yield _sse_event("status", status_payload)
                if status_value in {
                    AiJobStatus.SUCCEEDED.value,
                    AiJobStatus.FAILED.value,
                    AiJobStatus.CANCELLED.value,
                }:
                    yield _sse_event("complete", status_payload)
                    return
            except asyncio.CancelledError:
                return
            finally:
                if poll_db is not None:
                    poll_db.close()
            await asyncio.sleep(max(0.05, settings.ai_stream_poll_seconds))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/usage", response_model=list[UsageSummary])
def get_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return usage_summary_for_user(db, current_user.id)
