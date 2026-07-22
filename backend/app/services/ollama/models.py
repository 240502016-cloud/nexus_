from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


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
    model: str | None = None  # boşsa settings.ollama_default_model kullanılır
    title: str | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model: str
    title: str | None
    created_at: datetime


class MessageCreate(BaseModel):
    content: str


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
