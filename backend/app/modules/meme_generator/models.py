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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.platform.models import new_uuid, utcnow


class MemePlayerPreference(Base):
    __tablename__ = "meme_player_preferences"
    __table_args__ = (
        CheckConstraint(
            "maximum_harshness >= 0 AND maximum_harshness <= 2",
            name="ck_meme_preference_harshness",
        ),
    )

    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    memes_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_as_target: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_lore_references: Mapped[bool] = mapped_column(Boolean, default=True)
    maximum_harshness: Mapped[int] = mapped_column(Integer, default=1)
    blocked_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MemeGeneration(Base):
    __tablename__ = "meme_generations"
    __table_args__ = (
        UniqueConstraint("server_id", "external_event_id", name="uq_meme_generation_event"),
        UniqueConstraint(
            "server_id", "requested_by_id", "idempotency_key", name="uq_meme_generation_request"
        ),
        CheckConstraint(
            "meme_worthiness_score >= 0 AND meme_worthiness_score <= 1",
            name="ck_meme_generation_score",
        ),
        CheckConstraint(
            "desired_harshness >= 0 AND desired_harshness <= 2",
            name="ck_meme_generation_harshness",
        ),
        Index("ix_meme_generations_server_created", "server_id", "created_at"),
        Index("ix_meme_generations_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True
    )
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    background_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128))
    external_event_id: Mapped[str] = mapped_column(String(160))
    source: Mapped[str] = mapped_column(String(32))
    event_snapshot: Mapped[dict] = mapped_column(JSON)
    preferred_formats: Mapped[list[str]] = mapped_column(JSON, default=list)
    desired_harshness: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    meme_worthiness_score: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning_code: Mapped[str] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    eligible_template_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    candidates: Mapped[list["MemeCaptionCandidate"]] = relationship(
        back_populates="generation", cascade="all, delete-orphan", order_by="MemeCaptionCandidate.rank"
    )


class MemeCaptionCandidate(Base):
    __tablename__ = "meme_caption_candidates"
    __table_args__ = (
        UniqueConstraint("generation_id", "rank", name="uq_meme_candidate_rank"),
        CheckConstraint("rank >= 1 AND rank <= 3", name="ck_meme_candidate_rank"),
        CheckConstraint("harshness >= 0 AND harshness <= 2", name="ck_meme_candidate_harshness"),
        CheckConstraint("quality_score >= 0 AND quality_score <= 1", name="ck_meme_candidate_quality"),
        Index("ix_meme_candidates_generation", "generation_id", "created_at"),
        Index("ix_meme_candidates_phrase", "phrase_hash", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("meme_generations.id", ondelete="CASCADE")
    )
    rank: Mapped[int] = mapped_column(Integer)
    template_key: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40))
    captions: Mapped[dict] = mapped_column(JSON)
    target_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lore_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    harshness: Mapped[int] = mapped_column(Integer, default=1)
    quality_score: Mapped[float] = mapped_column(Float)
    phrase_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    generation: Mapped["MemeGeneration"] = relationship(back_populates="candidates")


class GeneratedMeme(Base):
    __tablename__ = "generated_memes"
    __table_args__ = (
        Index("ix_generated_memes_server_created", "server_id", "created_at"),
        Index("ix_generated_memes_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    generation_id: Mapped[str] = mapped_column(
        ForeignKey("meme_generations.id", ondelete="CASCADE")
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("meme_caption_candidates.id", ondelete="RESTRICT")
    )
    asset_id: Mapped[str] = mapped_column(
        ForeignKey("media_assets.id", ondelete="RESTRICT"), unique=True
    )
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    template_key: Mapped[str] = mapped_column(String(64))
    template_version: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40))
    captions_snapshot: Mapped[dict] = mapped_column(JSON)
    target_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    lore_references: Mapped[list[str]] = mapped_column(JSON, default=list)
    width: Mapped[int] = mapped_column(Integer, default=1200)
    height: Mapped[int] = mapped_column(Integer, default=1200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemeFeedback(Base):
    __tablename__ = "meme_feedback"
    __table_args__ = (
        UniqueConstraint("meme_id", "user_id", name="uq_meme_feedback_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    meme_id: Mapped[str] = mapped_column(
        ForeignKey("generated_memes.id", ondelete="CASCADE")
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    feedback_type: Mapped[str] = mapped_column(String(24))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

