from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.platform.models import new_uuid, utcnow


class StorySafetyProfile(Base):
    __tablename__ = "story_safety_profiles"
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    horror_level: Mapped[int] = mapped_column(Integer, default=1)
    violence_level: Mapped[int] = mapped_column(Integer, default=1)
    romance: Mapped[str] = mapped_column(String(16), default="OFF")
    player_conflict: Mapped[str] = mapped_column(String(16), default="COOPERATIVE")
    betrayal: Mapped[str] = mapped_column(String(16), default="OFF")
    personal_jokes: Mapped[bool] = mapped_column(Boolean, default=False)
    dark_humor: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StoryCharacter(Base):
    __tablename__ = "story_characters"
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    seat: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(60))
    archetype: Mapped[str] = mapped_column(String(32))
    traits: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoryState(Base):
    __tablename__ = "story_states"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_story_state_revision"),
        Index("ix_story_state_current", "session_id", "is_current"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    public_state: Mapped[dict] = mapped_column(JSON)
    private_state_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    rng_counter: Mapped[int] = mapped_column(Integer, default=0)
    rng_commitment: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(20), default="ACTION")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoryAction(Base):
    __tablename__ = "story_actions"
    __table_args__ = (UniqueConstraint("session_id", "user_id", "idempotency_key", name="uq_story_action_idempotency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chapter_number: Mapped[int] = mapped_column(Integer)
    scene_number: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    action_id: Mapped[str] = mapped_column(String(80))
    outcome: Mapped[str] = mapped_column(String(24))
    effect_payload: Mapped[dict] = mapped_column(JSON)
    applied_revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoryChoiceVote(Base):
    __tablename__ = "story_choice_votes"
    __table_args__ = (UniqueConstraint("session_id", "chapter_number", "user_id", name="uq_story_vote_chapter_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    chapter_number: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    encrypted_choice: Mapped[bytes] = mapped_column(LargeBinary)
    choice_commitment: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
