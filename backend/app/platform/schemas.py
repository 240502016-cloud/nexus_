from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class SeatedGameCreate(BaseModel):
    """İki veya üç koltuklu oyun modüllerinin ortak kurulum alanları.

    ``ai_players`` boş koltuğu AI'ın doldurmasını ister. Geçerli birleşimler:
    2 insan (2 koltuk) · 2 insan + 1 AI (3 koltuk) · 3 insan (3 koltuk).
    ``ai_roast_battle`` bu tabanı kullanmaz; o modül üç insana kilitli kalır.
    """

    player_ids: list[int] = Field(min_length=2, max_length=3)
    ai_players: int = Field(default=0, ge=0, le=1)

    @model_validator(mode="after")
    def _validate_seats(self) -> "SeatedGameCreate":
        if len(set(self.player_ids)) != len(self.player_ids):
            raise ValueError("player ids must be unique")
        if len(self.player_ids) + self.ai_players > 3:
            raise ValueError("a session can hold at most three seats")
        return self


class ExperienceCreate(BaseModel):
    module_type: str = Field(min_length=2, max_length=32, pattern=r"^[a-z][a-z0-9_]+$")
    channel_id: int | None = Field(default=None, gt=0)
    settings: dict[str, Any] = Field(default_factory=dict)


class RevisionCommand(BaseModel):
    expected_revision: int = Field(ge=0)


class ReadyCommand(RevisionCommand):
    ready: bool = True


class ExperiencePlayerRead(BaseModel):
    user_id: int
    username: str
    display_name: str | None
    seat: int
    ready: bool
    joined_at: datetime


class ExperienceRead(BaseModel):
    id: str
    module_type: str
    server_id: int
    channel_id: int | None
    owner_id: int
    status: str
    revision: int
    max_players: int
    settings_version: int
    settings: dict[str, Any]
    players: list[ExperiencePlayerRead]
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    updated_at: datetime


class ExperienceEventRead(BaseModel):
    id: int
    type: str
    schema_version: int
    session_id: str
    sequence: int
    revision: int
    audience: str
    occurred_at: datetime
    payload: dict[str, Any]


class ExperienceEventPage(BaseModel):
    items: list[ExperienceEventRead]
    last_sequence: int


class WsTicketRead(BaseModel):
    ticket: str
    expires_at: datetime


class BackgroundJobRead(BaseModel):
    id: str
    module: str
    job_type: str
    session_id: str | None
    status: str
    attempts: int
    cancel_requested: bool
    created_at: datetime
    completed_at: datetime | None
