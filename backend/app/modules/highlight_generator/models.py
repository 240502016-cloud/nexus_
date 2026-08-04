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


class HighlightRecording(Base):
    __tablename__ = "highlight_recordings"
    __table_args__ = (
        UniqueConstraint("server_id", "uploaded_by_id", "idempotency_key", name="uq_highlight_recording_request"),
        CheckConstraint("declared_byte_size >= 1 AND declared_byte_size <= 1073741824", name="ck_highlight_recording_declared_size"),
        CheckConstraint("byte_size IS NULL OR (byte_size >= 1 AND byte_size <= 1073741824)", name="ck_highlight_recording_size"),
        CheckConstraint("duration_ms IS NULL OR (duration_ms >= 1 AND duration_ms <= 900000)", name="ck_highlight_recording_duration"),
        Index("ix_highlight_recordings_server_created", "server_id", "created_at"),
        Index("ix_highlight_recordings_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id", ondelete="SET NULL"), unique=True, nullable=True)
    probe_job_id: Mapped[str | None] = mapped_column(ForeignKey("background_jobs.id", ondelete="SET NULL"), unique=True, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(32))
    original_filename: Mapped[str] = mapped_column(String(180))
    declared_mime_type: Mapped[str] = mapped_column(String(80))
    declared_byte_size: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str | None] = mapped_column(String(300), unique=True, nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_codec: Mapped[str | None] = mapped_column(String(40), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(40), nullable=True)
    has_audio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    probe_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="awaiting_upload")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    markers: Mapped[list["HighlightMarker"]] = relationship(back_populates="recording", cascade="all, delete-orphan")


class HighlightMarker(Base):
    __tablename__ = "highlight_markers"
    __table_args__ = (
        UniqueConstraint("recording_id", "external_marker_id", name="uq_highlight_marker_external"),
        CheckConstraint("offset_ms >= 0", name="ck_highlight_marker_offset"),
        CheckConstraint("manual_priority >= 0 AND manual_priority <= 1", name="ck_highlight_marker_priority"),
        Index("ix_highlight_markers_timeline", "recording_id", "offset_ms"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("highlight_recordings.id", ondelete="CASCADE"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    external_marker_id: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(24))
    offset_ms: Mapped[int] = mapped_column(Integer)
    category_hint: Mapped[str | None] = mapped_column(String(24), nullable=True)
    participant_player_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    manual_priority: Mapped[int] = mapped_column(Integer, default=1)
    commentator_priority: Mapped[float | None] = mapped_column(Float, nullable=True)
    game_event_severity: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    recording: Mapped["HighlightRecording"] = relationship(back_populates="markers")
    candidate: Mapped["HighlightCandidate | None"] = relationship(back_populates="marker", uselist=False)


class HighlightCandidate(Base):
    __tablename__ = "highlight_candidates"
    __table_args__ = (
        CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_highlight_candidate_window"),
        CheckConstraint("end_ms - start_ms <= 60000", name="ck_highlight_candidate_max_duration"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_highlight_candidate_score"),
        Index("ix_highlight_candidates_recording", "recording_id", "score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    recording_id: Mapped[str] = mapped_column(ForeignKey("highlight_recordings.id", ondelete="CASCADE"))
    marker_id: Mapped[str] = mapped_column(ForeignKey("highlight_markers.id", ondelete="CASCADE"), unique=True)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    anchor_ms: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    primary_category: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300))
    participant_player_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    signal_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    lore_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    meme_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    analysis_version: Mapped[str] = mapped_column(String(40), default="highlight-score-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    marker: Mapped["HighlightMarker"] = relationship(back_populates="candidate")


class RenderedHighlight(Base):
    __tablename__ = "rendered_highlights"
    __table_args__ = (
        UniqueConstraint("candidate_id", "variant", name="uq_rendered_highlight_variant"),
        Index("ix_rendered_highlights_server_created", "server_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("highlight_candidates.id", ondelete="CASCADE"))
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(ForeignKey("experience_sessions.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    render_job_id: Mapped[str | None] = mapped_column(ForeignKey("background_jobs.id", ondelete="SET NULL"), unique=True, nullable=True)
    video_asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id", ondelete="SET NULL"), unique=True, nullable=True)
    thumbnail_asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id", ondelete="SET NULL"), unique=True, nullable=True)
    variant: Mapped[str] = mapped_column(String(24), default="landscape")
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300))
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    render_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HighlightFeedback(Base):
    __tablename__ = "highlight_feedback"
    __table_args__ = (UniqueConstraint("highlight_id", "user_id", name="uq_highlight_feedback_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    highlight_id: Mapped[str] = mapped_column(ForeignKey("rendered_highlights.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    feedback_type: Mapped[str] = mapped_column(String(24))
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

