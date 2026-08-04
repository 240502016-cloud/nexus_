from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.platform.models import new_uuid, utcnow


class CommentatorPlayerPreference(Base):
    __tablename__ = "commentator_player_preferences"
    __table_args__ = (
        CheckConstraint(
            "maximum_harshness >= 0 AND maximum_harshness <= 3",
            name="ck_commentator_preference_harshness",
        ),
    )

    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    commentary_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_targeted_jokes: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_lore_references: Mapped[bool] = mapped_column(Boolean, default=True)
    maximum_harshness: Mapped[int] = mapped_column(Integer, default=1)
    preferred_humor_styles: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["GENTLE"])
    blocked_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    tts_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommentatorSessionPlayer(Base):
    __tablename__ = "commentator_session_players"
    __table_args__ = (
        CheckConstraint("targeted_count >= 0", name="ck_commentator_session_targeted_count"),
        Index("ix_commentator_session_players_user", "user_id", "session_id"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preference_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    targeted_count: Mapped[int] = mapped_column(Integer, default=0)
    is_present: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommentatorEvent(Base):
    __tablename__ = "commentator_events"
    __table_args__ = (
        CheckConstraint("importance >= 0 AND importance <= 1", name="ck_commentator_event_importance"),
        CheckConstraint(
            "source_confidence >= 0 AND source_confidence <= 1",
            name="ck_commentator_event_confidence",
        ),
        CheckConstraint("novelty_score >= 0 AND novelty_score <= 1", name="ck_commentator_event_novelty"),
        CheckConstraint("trigger_score >= 0 AND trigger_score <= 1", name="ck_commentator_event_trigger"),
        UniqueConstraint("session_id", "external_event_id", name="uq_commentator_event_external"),
        Index("ix_commentator_events_recent", "session_id", "occurred_at"),
        Index("ix_commentator_events_dedup", "session_id", "deduplication_key", "occurred_at"),
        Index("ix_commentator_events_state", "processing_state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("experience_sessions.id", ondelete="CASCADE")
    )
    external_event_id: Mapped[str] = mapped_column(String(160))
    schema_version: Mapped[str] = mapped_column(String(8), default="1.0")
    source: Mapped[str] = mapped_column(String(24))
    category: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_player_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    target_player_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    normalized_summary: Mapped[str] = mapped_column(String(240))
    game_context: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    importance: Mapped[float] = mapped_column(Float)
    source_confidence: Mapped[float] = mapped_column(Float)
    novelty_score: Mapped[float] = mapped_column(Float, default=0.5)
    trigger_score: Mapped[float] = mapped_column(Float, default=0.0)
    trigger_decision: Mapped[str] = mapped_column(String(24))
    deduplication_key: Mapped[str] = mapped_column(String(64))
    processing_state: Mapped[str] = mapped_column(String(24), default="pending")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    commentary: Mapped["GeneratedCommentary | None"] = relationship(
        back_populates="primary_event", uselist=False
    )


class GeneratedCommentary(Base):
    __tablename__ = "generated_commentary"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_generated_commentary_confidence"),
        CheckConstraint(
            "(should_comment AND commentary_text IS NOT NULL) OR "
            "(NOT should_comment AND commentary_text IS NULL)",
            name="ck_generated_commentary_shape",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_generated_commentary_latency"),
        Index("ix_generated_commentary_history", "session_id", "created_at"),
        Index("ix_generated_commentary_target", "session_id", "target_player_id", "created_at"),
        Index("ix_generated_commentary_phrase", "session_id", "phrase_hash", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("experience_sessions.id", ondelete="CASCADE")
    )
    primary_event_id: Mapped[str] = mapped_column(
        ForeignKey("commentator_events.id", ondelete="CASCADE"), unique=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    source_event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    profile_key: Mapped[str] = mapped_column(String(64))
    should_comment: Mapped[bool] = mapped_column(Boolean)
    commentary_text: Mapped[str | None] = mapped_column(String(240), nullable=True)
    target_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tone: Mapped[str | None] = mapped_column(String(16), nullable=True)
    lore_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    reason_code: Mapped[str] = mapped_column(String(32))
    model_profile: Mapped[str] = mapped_column(String(80), default="commentary-live")
    provider_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(40), default="commentator-live-v1")
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phrase_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dispatch_state: Mapped[str] = mapped_column(String(24), default="pending")
    dispatch_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    primary_event: Mapped["CommentatorEvent"] = relationship(back_populates="commentary")


class CommentaryFeedback(Base):
    __tablename__ = "commentary_feedback"
    __table_args__ = (
        UniqueConstraint("commentary_id", "user_id", name="uq_commentary_feedback_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    commentary_id: Mapped[str] = mapped_column(
        ForeignKey("generated_commentary.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    feedback_type: Mapped[str] = mapped_column(String(24))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CommentaryCooldown(Base):
    __tablename__ = "commentary_cooldowns"
    __table_args__ = (
        CheckConstraint("usage_count >= 1", name="ck_commentary_cooldown_usage"),
        UniqueConstraint("session_id", "scope_type", "scope_key", name="uq_commentary_cooldown"),
        Index("ix_commentary_cooldowns_active", "session_id", "cooldown_until"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("experience_sessions.id", ondelete="CASCADE")
    )
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_key: Mapped[str] = mapped_column(String(160))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
