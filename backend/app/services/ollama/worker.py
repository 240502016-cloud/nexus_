"""Durable PostgreSQL-backed AI worker.

The API only commits a user message and a queued ``AiJob``. This process claims jobs with
``FOR UPDATE SKIP LOCKED``, performs the blocking Ollama call outside a database transaction,
then records the assistant message in a short final transaction. A lease makes a job recoverable
when the worker is killed during generation; retry policy is deliberately separate from the
HTTP client's small upstream retry policy.
"""

from __future__ import annotations

import logging
import signal
import time
import uuid
from datetime import datetime, timedelta, timezone
from threading import Event

from sqlalchemy import and_, or_, select

from app.config import settings
from app.database import SessionLocal
from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Bot, Channel
from app.services.ollama.client import (
    DEFAULT_SYSTEM_PROMPT,
    OllamaError,
    OllamaGatewayTimeoutError,
    OllamaGatewayUnavailableError,
    ollama_client,
)
from app.services.ollama.models import (
    AiBotJob,
    AiConversation,
    AiJob,
    AiJobStatus,
    AiMessage,
    MessageRole,
    QueuedAiResponse,
)
from app.services.ollama.tokenizer import TokenUsage, record_usage
from app.services.ollama.tokenizer import build_token_limited_context

logger = logging.getLogger("nexus.ai_worker")
WORKER_ID = f"ai-worker-{uuid.uuid4()}"
STOP = Event()
MAX_CONTEXT_MESSAGES = 200


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_bot_question(context: object) -> QueuedAiResponse | None:
    """Persist a channel `/sor` request without storing Matrix credentials in the job."""
    bot_id = getattr(context, "bot_id", None)
    channel_id = getattr(context, "channel_id", None)
    user_id = getattr(context, "user_id", None)
    question = (getattr(context, "args", "") or "").strip()
    if not bot_id or not channel_id or not user_id or not question:
        return None
    db = SessionLocal()
    try:
        job = AiBotJob(bot_id=bot_id, channel_id=channel_id, user_id=user_id, question=question)
        db.add(job)
        db.commit()
        db.refresh(job)
        return QueuedAiResponse(job_id=job.id)
    finally:
        db.close()


def _claim_next_job() -> tuple[int, int] | None:
    """Claim one queued or expired-lease job and return (id, attempt number)."""
    db = SessionLocal()
    try:
        now = utcnow()
        job = db.execute(
            select(AiJob)
            .where(
                or_(
                    and_(AiJob.status == AiJobStatus.QUEUED, AiJob.next_attempt_at <= now),
                    and_(AiJob.status == AiJobStatus.RUNNING, AiJob.lease_expires_at < now),
                )
            )
            .order_by(AiJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            db.rollback()
            return None

        job.status = AiJobStatus.RUNNING
        job.attempts += 1
        job.locked_by = WORKER_ID
        job.started_at = now
        job.lease_expires_at = now + timedelta(seconds=max(30, settings.ai_worker_lease_seconds))
        job.output_text = None
        db.commit()
        return job.id, job.attempts
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _load_job(job_id: int) -> tuple[int, str, list[dict], bool, str] | None:
    db = SessionLocal()
    try:
        job = db.get(AiJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return None
        conversation = db.get(AiConversation, job.conversation_id)
        if conversation is None:
            return None
        history = (
            db.query(AiMessage)
            .filter(
                AiMessage.conversation_id == job.conversation_id,
                AiMessage.id <= job.user_message_id,
            )
            .order_by(AiMessage.id.desc())
            .limit(MAX_CONTEXT_MESSAGES)
            .all()
        )
        history.reverse()
        raw_messages = [{"role": item.role.value, "content": item.content} for item in history]
        messages = build_token_limited_context(
            raw_messages,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            token_budget=settings.ai_context_token_budget,
        )
        return job.attempts, conversation.model, messages, bool(job.cancel_requested), job.output_text or ""
    finally:
        db.close()


def _update_output(job_id: int, output_text: str) -> bool:
    db = SessionLocal()
    try:
        job = db.get(AiJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return False
        if job.cancel_requested:
            return False
        job.output_text = output_text
        db.commit()
        return True
    finally:
        db.close()


def _cancel_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(AiJob, job_id)
        if not job or job.status not in (AiJobStatus.QUEUED, AiJobStatus.RUNNING):
            return
        if job.status == AiJobStatus.RUNNING and job.locked_by != WORKER_ID:
            return
        job.status = AiJobStatus.CANCELLED
        job.cancel_requested = True
        job.locked_by = None
        job.lease_expires_at = None
        job.completed_at = utcnow()
        db.commit()
    finally:
        db.close()


def _complete_job(job_id: int, response: dict, output_text: str) -> bool:
    db = SessionLocal()
    try:
        job = db.get(AiJob, job_id)
        if (
            not job
            or job.status != AiJobStatus.RUNNING
            or job.locked_by != WORKER_ID
            or job.cancel_requested
        ):
            return False
        reply = output_text or response.get("message", {}).get("content", "")
        conversation = db.get(AiConversation, job.conversation_id)
        if conversation is None:
            db.rollback()
            return False
        assistant = AiMessage(
            conversation_id=job.conversation_id, role=MessageRole.ASSISTANT, content=reply
        )
        db.add(assistant)
        db.flush()
        record_usage(
            db,
            user_id=job.user_id,
            conversation_id=job.conversation_id,
            model=conversation.model,
            usage=TokenUsage.from_ollama_response(response),
        )
        job.assistant_message_id = assistant.id
        job.status = AiJobStatus.SUCCEEDED
        job.locked_by = None
        job.lease_expires_at = None
        job.error = None
        job.completed_at = utcnow()
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _fail_job(job_id: int, attempts: int, exc: Exception) -> None:
    db = SessionLocal()
    try:
        job = db.get(AiJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return
        if job.cancel_requested:
            job.status = AiJobStatus.CANCELLED
            job.completed_at = utcnow()
            job.locked_by = None
            job.lease_expires_at = None
            db.commit()
            return
        retryable = isinstance(exc, (OllamaGatewayUnavailableError, OllamaGatewayTimeoutError))
        if retryable and attempts < max(1, settings.ai_worker_max_attempts):
            delay = max(0.1, settings.ai_worker_retry_backoff_seconds) * (2 ** max(0, attempts - 1))
            job.status = AiJobStatus.QUEUED
            job.next_attempt_at = utcnow() + timedelta(seconds=delay)
        else:
            job.status = AiJobStatus.FAILED
            job.completed_at = utcnow()
        job.error = str(exc)[:1000]
        job.locked_by = None
        job.lease_expires_at = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _claim_next_bot_job() -> tuple[int, int] | None:
    db = SessionLocal()
    try:
        now = utcnow()
        job = db.execute(
            select(AiBotJob)
            .where(
                or_(
                    and_(AiBotJob.status == AiJobStatus.QUEUED, AiBotJob.next_attempt_at <= now),
                    and_(AiBotJob.status == AiJobStatus.RUNNING, AiBotJob.lease_expires_at < now),
                )
            )
            .order_by(AiBotJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            db.rollback()
            return None
        job.status = AiJobStatus.RUNNING
        job.attempts += 1
        job.locked_by = WORKER_ID
        job.lease_expires_at = now + timedelta(seconds=max(30, settings.ai_worker_lease_seconds))
        db.commit()
        return job.id, job.attempts
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _load_bot_job(job_id: int) -> tuple[int, str | None, str | None, str | None] | None:
    db = SessionLocal()
    try:
        job = db.get(AiBotJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return None
        bot = db.get(Bot, job.bot_id)
        channel = db.get(Channel, job.channel_id)
        if not bot or not channel:
            return None
        return job.attempts, bot.matrix_access_token, channel.matrix_room_id, job.result_text
    finally:
        db.close()


def _store_bot_result(job_id: int, result: str) -> bool:
    db = SessionLocal()
    try:
        job = db.get(AiBotJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return False
        job.result_text = result
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _finish_bot_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(AiBotJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return
        job.status = AiJobStatus.SUCCEEDED
        job.locked_by = None
        job.lease_expires_at = None
        job.error = None
        job.completed_at = utcnow()
        db.commit()
    finally:
        db.close()


def _fail_bot_job(job_id: int, attempts: int, exc: Exception) -> None:
    db = SessionLocal()
    try:
        job = db.get(AiBotJob, job_id)
        if not job or job.status != AiJobStatus.RUNNING or job.locked_by != WORKER_ID:
            return
        retryable = isinstance(exc, (OllamaGatewayUnavailableError, OllamaGatewayTimeoutError, MatrixError))
        if retryable and attempts < max(1, settings.ai_worker_max_attempts):
            job.status = AiJobStatus.QUEUED
            job.next_attempt_at = utcnow() + timedelta(
                seconds=max(0.1, settings.ai_worker_retry_backoff_seconds) * (2 ** max(0, attempts - 1))
            )
        else:
            job.status = AiJobStatus.FAILED
            job.completed_at = utcnow()
        job.error = str(exc)[:1000]
        job.locked_by = None
        job.lease_expires_at = None
        db.commit()
    finally:
        db.close()


def process_bot_one() -> bool:
    claimed = _claim_next_bot_job()
    if claimed is None:
        return False
    job_id, attempts = claimed
    try:
        context = _load_bot_job(job_id)
        if context is None:
            return True
        _attempts, access_token, room_id, result = context
        if not result:
            db = SessionLocal()
            try:
                job = db.get(AiBotJob, job_id)
                question = job.question if job else None
            finally:
                db.close()
            if not question:
                raise OllamaError("AI bot işi sorusuz")
            response = ollama_client.chat(
                settings.ollama_default_model,
                [
                    {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                options={"num_predict": settings.ai_max_output_tokens},
            )
            result = response.get("message", {}).get("content", "")
            if not _store_bot_result(job_id, result):
                return True
        if not access_token or not room_id:
            raise MatrixError("AI botunun Matrix hesabı veya kanal odası yok")
        matrix_client.send_message(access_token, room_id, result, txn_id=f"nexus-ai-job-{job_id}")
        _finish_bot_job(job_id)
    except (OllamaError, MatrixError) as exc:
        logger.warning("AI bot işi başarısız: job_id=%s attempt=%s error=%s", job_id, attempts, exc)
        _fail_bot_job(job_id, attempts, exc)
    except Exception as exc:
        logger.exception("AI bot worker beklenmeyen hata: job_id=%s", job_id)
        _fail_bot_job(job_id, attempts, exc)
    return True


def process_one() -> bool:
    claimed = _claim_next_job()
    if claimed is None:
        return process_bot_one()
    job_id, attempts = claimed
    try:
        context = _load_job(job_id)
        if context is None:
            return True
        attempts, model, messages, cancelled, output_text = context
        if cancelled:
            _cancel_job(job_id)
            return True
        response: dict = {}
        last_flush = time.monotonic()
        for chunk, payload in ollama_client.chat_stream(
            model,
            messages,
            options={"num_predict": settings.ai_max_output_tokens},
        ):
            if chunk:
                output_text += chunk
            if time.monotonic() - last_flush >= max(0.05, settings.ai_stream_poll_seconds):
                if not _update_output(job_id, output_text):
                    _cancel_job(job_id)
                    return True
                last_flush = time.monotonic()
            if payload.get("done"):
                response = payload
        if not _update_output(job_id, output_text):
            _cancel_job(job_id)
            return True
        if not _complete_job(job_id, response, output_text):
            logger.warning("AI işi fencing nedeniyle tamamlanmadı: job_id=%s", job_id)
            _cancel_job(job_id)
    except OllamaError as exc:
        logger.warning("AI işi başarısız: job_id=%s attempt=%s error=%s", job_id, attempts, exc)
        _fail_job(job_id, attempts, exc)
    except Exception as exc:
        logger.exception("AI worker beklenmeyen hata: job_id=%s", job_id)
        _fail_job(job_id, attempts, exc)
    return True


def run() -> None:
    logger.info("AI worker başladı: worker_id=%s", WORKER_ID)
    while not STOP.is_set():
        try:
            did_work = process_one()
        except Exception:
            logger.exception("AI worker claim/işleme döngüsünde hata")
            did_work = False
        if not did_work:
            STOP.wait(max(0.05, settings.ai_worker_poll_seconds))
    logger.info("AI worker durdu: worker_id=%s", WORKER_ID)


def _request_stop(_signum: int, _frame: object) -> None:
    STOP.set()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    run()
