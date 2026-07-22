from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class AiJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AiConversation(Base):
    """Bir kullanıcının bir model ile sürdürdüğü sohbet - "Sohbet geçmişi" ve
    "Context yönetimi" burada karşılanır: yeni bir mesaj gönderildiğinde, bu
    conversation'daki önceki mesajlar Ollama'ya context olarak geri gönderilir."""

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    messages: Mapped[list["AiMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="AiMessage.id"
    )


class AiMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["AiConversation"] = relationship(back_populates="messages")


class AiJob(Base):
    """PostgreSQL-backed AI work item.

    The prompt is committed before any network call. A separate worker claims the row with a
    lease, so API requests stay short and queued work survives an API/worker restart.
    """

    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_message_id: Mapped[int] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="CASCADE"), unique=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    assistant_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_messages.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[AiJobStatus] = mapped_column(String(16), default=AiJobStatus.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiBotJob(Base):
    """Queued `/sor` bot command; the worker posts the result to Matrix after generation."""

    __tablename__ = "ai_bot_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AiJobStatus] = mapped_column(String(16), default=AiJobStatus.QUEUED, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiTokenUsage(Base):
    """"Token kullanım takibi": her Ollama çağrısından sonra, modelin kendi döndürdüğü
    gerçek prompt_eval_count/eval_count değerleri buraya kaydedilir - ayrı bir tahmini
    tokenizer kütüphanesine ihtiyaç yoktur (bkz. tokenizer.py)."""

    __tablename__ = "ai_token_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    conversation_id: Mapped[int] = mapped_column(ForeignKey("ai_conversations.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---- Pydantic şemaları ----


class ConversationCreate(BaseModel):
    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:-]{0,99}$",
    )  # boşsa settings.ollama_default_model kullanılır
    title: str | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    title: str | None
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class AiJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    user_message_id: int
    assistant_message_id: int | None
    status: AiJobStatus
    attempts: int
    output_text: str | None
    cancel_requested: bool
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class QueuedAiResponse:
    job_id: int


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime


class ModelInfo(BaseModel):
    name: str
    size: int | None = None


class UsageSummary(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class GatewayHealth(BaseModel):
    status: str
    models: list[str]
