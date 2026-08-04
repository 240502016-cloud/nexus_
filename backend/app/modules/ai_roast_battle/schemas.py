from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


GamingTopic = Literal["GAMING_MISTAKES", "FAILED_STRATEGIES", "MATCH_STATISTICS", "FUNNY_HIGHLIGHTS", "CONFIRMED_PARTY_LORE", "NAVIGATION", "TEAMWORK", "INVENTORY", "TIMING", "REACTIONS"]


class RoastProfileUpdate(BaseModel):
    roast_enabled: bool
    maximum_intensity: int = Field(default=1, ge=0, le=2)
    allowed_topics: list[GamingTopic] = Field(default_factory=list, max_length=10)
    allow_party_lore: bool = False
    allow_highlights: bool = True
    allow_recent_failures: bool = False
    blocked_terms: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("blocked_terms")
    @classmethod
    def clean_terms(cls, value: list[str]) -> list[str]:
        return sorted({" ".join(item.split()).casefold()[:80] for item in value if item.strip()})


class RoastProfileRead(RoastProfileUpdate):
    model_config = ConfigDict(from_attributes=True)
    server_id: int
    user_id: int
    consent_version: int
    updated_at: datetime


class RoastSessionCreate(BaseModel):
    player_ids: list[int] = Field(min_length=3, max_length=3)
    requested_intensity: int = Field(default=1, ge=0, le=2)

    @field_validator("player_ids")
    @classmethod
    def three_unique(cls, value: list[int]) -> list[int]:
        if len(set(value)) != 3:
            raise ValueError("exactly three unique players are required")
        return value


class RoastConsentCreate(BaseModel):
    decision: Literal["READY", "DECLINE", "REVOKE"]
    consent_version: int = Field(ge=1)


class RoastSessionRead(BaseModel):
    id: str
    server_id: int
    player_ids: list[int]
    consent: dict[int, str]
    requested_intensity: int
    status: str
    current_round: int
    revision: int


class RoastRoundRead(BaseModel):
    id: str
    session_id: str
    round_number: int
    target_player_id: int
    effective_intensity: int
    status: str
    candidate_id: str | None
    roast_text: str | None
    angle: str | None


class RoastVoteCreate(BaseModel):
    vote: Literal["FUNNY", "OKAY", "PASS"]

