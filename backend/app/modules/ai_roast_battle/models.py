from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.platform.models import new_uuid, utcnow


class RoastProfile(Base):
    __tablename__ = "roast_profiles"
    __table_args__ = (CheckConstraint("maximum_intensity >= 0 AND maximum_intensity <= 2", name="ck_roast_profile_intensity"),)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    roast_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    maximum_intensity: Mapped[int] = mapped_column(Integer, default=1)
    allowed_topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    allow_party_lore: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_highlights: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_recent_failures: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    consent_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RoastSessionPlayer(Base):
    __tablename__ = "roast_session_players"
    __table_args__ = (UniqueConstraint("session_id", "seat", name="uq_roast_session_player_seat"),)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    seat: Mapped[int] = mapped_column(Integer)
    consent_state: Mapped[str] = mapped_column(String(16), default="pending")
    consent_version: Mapped[int] = mapped_column(Integer)
    profile_snapshot: Mapped[dict] = mapped_column(JSON)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoastRound(Base):
    __tablename__ = "roast_rounds"
    __table_args__ = (
        UniqueConstraint("session_id", "round_number", name="uq_roast_round_number"),
        Index("ix_roast_rounds_session", "session_id", "round_number"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer)
    target_player_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    effective_intensity: Mapped[int] = mapped_column(Integer)
    source_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="generating")
    selected_candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RoastCandidate(Base):
    __tablename__ = "roast_candidates"
    __table_args__ = (
        CheckConstraint("intensity >= 0 AND intensity <= 2", name="ck_roast_candidate_intensity"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_roast_candidate_confidence"),
        Index("ix_roast_candidates_target_created", "target_player_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    round_id: Mapped[str] = mapped_column(ForeignKey("roast_rounds.id", ondelete="CASCADE"), unique=True)
    target_player_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    roast_text: Mapped[str] = mapped_column(String(280))
    phrase_hash: Mapped[str] = mapped_column(String(64))
    angle: Mapped[str] = mapped_column(String(40))
    intensity: Mapped[int] = mapped_column(Integer)
    source_lore_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    displayed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoastVote(Base):
    __tablename__ = "roast_votes"
    __table_args__ = (UniqueConstraint("candidate_id", "voter_id", name="uq_roast_vote_user"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("roast_candidates.id", ondelete="CASCADE"))
    voter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    vote_type: Mapped[str] = mapped_column(String(12))
    is_target_vote: Mapped[bool] = mapped_column(Boolean, default=False)
    score_contribution: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

