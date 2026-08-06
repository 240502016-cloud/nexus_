from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.platform.models import new_uuid, utcnow


class BoardGameState(Base):
    __tablename__ = "board_game_states"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_board_game_state_revision"),
        Index("ix_board_game_state_current", "session_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    public_state: Mapped[dict] = mapped_column(JSON)
    engine_state: Mapped[dict] = mapped_column(JSON)
    rng_commitment: Mapped[str] = mapped_column(String(64))
    rng_counter: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BoardGameAction(Base):
    __tablename__ = "board_game_actions"
    __table_args__ = (
        UniqueConstraint("session_id", "actor_id", "idempotency_key", name="uq_board_game_action_idempotency"),
        Index("ix_board_game_actions_session_revision", "session_id", "applied_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("experience_sessions.id", ondelete="CASCADE"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    action_id: Mapped[str] = mapped_column(String(80))
    expected_revision: Mapped[int] = mapped_column(Integer)
    applied_revision: Mapped[int] = mapped_column(Integer)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
