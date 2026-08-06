from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.platform.schemas import SeatedGameCreate


class BoardGameCreate(SeatedGameCreate):
    theme: Literal["ARCANE_RUINS", "SPACE_WRECK", "CURSED_CARNIVAL"] = "ARCANE_RUINS"


class BoardActionCommand(BaseModel):
    action_id: str = Field(min_length=3, max_length=80)
    action_token: str = Field(min_length=32, max_length=128)
    expected_revision: int = Field(ge=1)


class BoardGameView(BaseModel):
    session_id: str
    server_id: int
    status: str
    revision: int
    rules_version: str
    theme: str
    round: int
    maximum_rounds: int
    active_user_id: int | None
    active_seat: int | None
    active_is_ai: bool
    seat_count: int
    action_points: int
    chaos: int
    chaos_limit: int
    portal_charge: int
    deposited_sigils: list[str]
    players: list[dict]
    tiles: dict[str, dict]
    legal_actions: list[dict]
    events: list[dict]
    group_outcome: str | None
    winner_user_id: int | None
    end_reason: str | None
    rng_commitment: str
    rng_seed_reveal: str | None
