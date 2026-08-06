from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.platform.models import new_uuid, utcnow

class EscapeRoomState(Base):
    __tablename__ = "escape_room_states"
    __table_args__ = (UniqueConstraint("session_id", "revision", name="uq_escape_state_revision"), Index("ix_escape_state_current", "session_id", "is_current"))
    id: Mapped[int] = mapped_column(primary_key=True); session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE")); revision: Mapped[int] = mapped_column(Integer); is_current: Mapped[bool] = mapped_column(Boolean, default=True); public_state: Mapped[dict] = mapped_column(JSON); engine_ciphertext: Mapped[bytes] = mapped_column(LargeBinary); rng_commitment: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EscapePrivateConsole(Base):
    __tablename__ = "escape_private_consoles"
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True); user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True); role: Mapped[str] = mapped_column(String(16)); encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EscapeAttempt(Base):
    __tablename__ = "escape_attempts"
    __table_args__ = (UniqueConstraint("session_id", "user_id", "idempotency_key", name="uq_escape_attempt_idempotency"), Index("ix_escape_attempt_duplicate", "session_id", "node_id", "user_id", "answer_hash"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE")); node_id: Mapped[str] = mapped_column(String(8)); user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE")); idempotency_key: Mapped[str] = mapped_column(String(128)); answer_hash: Mapped[str] = mapped_column(String(64)); result: Mapped[str] = mapped_column(String(20)); state_revision: Mapped[int] = mapped_column(Integer); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EscapeSimultaneousSubmission(Base):
    __tablename__ = "escape_simultaneous_submissions"
    __table_args__ = (UniqueConstraint("session_id", "node_id", "user_id", name="uq_escape_sim_submission_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE")); node_id: Mapped[str] = mapped_column(String(8)); user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE")); encrypted_value: Mapped[bytes] = mapped_column(LargeBinary); value_hash: Mapped[str] = mapped_column(String(64)); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EscapeHintDelivery(Base):
    __tablename__ = "escape_hint_deliveries"
    __table_args__ = (UniqueConstraint("session_id", "node_id", "user_id", "tier", name="uq_escape_hint_delivery"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE")); node_id: Mapped[str] = mapped_column(String(8)); user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE")); tier: Mapped[int] = mapped_column(Integer); text: Mapped[str] = mapped_column(String(400)); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class EscapeFinalAssistConsent(Base):
    __tablename__ = "escape_final_assist_consents"
    __table_args__ = (UniqueConstraint("session_id", "node_id", "user_id", name="uq_escape_assist_consent"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid); session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE")); node_id: Mapped[str] = mapped_column(String(8)); user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE")); created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
