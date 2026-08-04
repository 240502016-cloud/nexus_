from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.platform.models import new_uuid, utcnow


class LoreCandidate(Base):
    __tablename__ = "lore_candidates"
    __table_args__ = (
        UniqueConstraint(
            "server_id",
            "submitted_by_id",
            "idempotency_key",
            name="uq_lore_candidate_idempotency",
        ),
        Index("ix_lore_candidates_server_status", "server_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="moment")
    sensitivity: Mapped[str] = mapped_column(String(16), default="low")
    allowed_modules: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list["LoreCandidateParticipant"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="LoreCandidateParticipant.user_id",
    )
    entry: Mapped["LoreEntry | None"] = relationship(back_populates="candidate", uselist=False)


class LoreCandidateParticipant(Base):
    __tablename__ = "lore_candidate_participants"
    __table_args__ = (Index("ix_lore_candidate_participants_user", "user_id", "decision"),)

    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("lore_candidates.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    decision: Mapped[str] = mapped_column(String(16), default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate: Mapped["LoreCandidate"] = relationship(back_populates="participants")


class LoreEntry(Base):
    __tablename__ = "lore_entries"
    __table_args__ = (
        Index("ix_lore_entries_retrieve", "server_id", "status", "sensitivity"),
        Index("ix_lore_entries_category", "server_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("lore_candidates.id", ondelete="CASCADE"), unique=True
    )
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32))
    sensitivity: Mapped[str] = mapped_column(String(16))
    allowed_modules: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate: Mapped["LoreCandidate"] = relationship(back_populates="entry")
    participants: Mapped[list["LoreParticipant"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="LoreParticipant.user_id",
    )
    evidence: Mapped[list["LoreEvidence"]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class LoreParticipant(Base):
    __tablename__ = "lore_participants"
    __table_args__ = (Index("ix_lore_participants_user", "user_id", "consent_state"),)

    lore_id: Mapped[str] = mapped_column(
        ForeignKey("lore_entries.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    consent_state: Mapped[str] = mapped_column(String(16), default="confirmed")
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entry: Mapped["LoreEntry"] = relationship(back_populates="participants")


class LoreEvidence(Base):
    __tablename__ = "lore_evidence"
    __table_args__ = (Index("ix_lore_evidence_entry", "lore_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    lore_id: Mapped[str] = mapped_column(ForeignKey("lore_entries.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    entry: Mapped["LoreEntry"] = relationship(back_populates="evidence")


class LoreUsage(Base):
    __tablename__ = "lore_usage"
    __table_args__ = (
        UniqueConstraint("request_id", "lore_id", name="uq_lore_usage_request_entry"),
        Index("ix_lore_usage_server_created", "server_id", "created_at"),
        Index("ix_lore_usage_entry_created", "lore_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    request_id: Mapped[str] = mapped_column(String(128))
    lore_id: Mapped[str] = mapped_column(ForeignKey("lore_entries.id", ondelete="CASCADE"))
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    module: Mapped[str] = mapped_column(String(32))
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
