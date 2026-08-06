from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.platform.models import new_uuid, utcnow


class HiddenRoleState(Base):
    __tablename__ = "hidden_role_states"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_hidden_role_state_revision"),
        Index("ix_hidden_role_state_current", "session_id", "is_current"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    public_state: Mapped[dict] = mapped_column(JSON)
    engine_ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    rng_commitment: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HiddenRoleAssignment(Base):
    __tablename__ = "hidden_role_assignments"
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HiddenRoleClaim(Base):
    __tablename__ = "hidden_role_claims"
    __table_args__ = (UniqueConstraint("session_id", "round_number", "user_id", name="uq_hidden_role_claim_round_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    subject_option_id: Mapped[str] = mapped_column(String(1))
    proposition: Mapped[str] = mapped_column(String(24))
    flavor_text: Mapped[str] = mapped_column(Text, default="")
    verdict: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HiddenRoleVote(Base):
    __tablename__ = "hidden_role_votes"
    __table_args__ = (UniqueConstraint("session_id", "round_number", "user_id", name="uq_hidden_role_vote_round_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HiddenRoleDeduction(Base):
    __tablename__ = "hidden_role_deductions"
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_hidden_role_deduction_user"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
