from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MemeSource = Literal["MANUAL", "COMMENTARY_EVENT", "HIGHLIGHT", "GAME_CONNECTOR"]
MomentType = Literal[
    "FAILURE", "SUCCESS", "BETRAYAL", "TEAM_EVENT", "MILESTONE", "PREPARATION",
    "NAVIGATION", "PANIC", "SILENCE", "MANUAL_NOTE",
]
MemeFormat = Literal[
    "TEXT_CARD", "CAPTIONED_TEMPLATE", "ACHIEVEMENT_CARD", "PATCH_NOTES",
    "NEWS_REPORT", "PLAYER_STATS", "EXPECTATION_REALITY", "REACTION_CARD",
]


class MemeGameContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    game_key: str = Field(min_length=1, max_length=80)
    match_id: str | None = Field(default=None, max_length=160)
    round_id: str | None = Field(default=None, max_length=160)
    mode: str | None = Field(default=None, max_length=80)
    map: str | None = Field(default=None, max_length=80)


class MemeFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: Literal["durationSeconds", "attemptCount", "itemsLost", "healthRemaining", "teamSize"]
    value: str | int | float | bool


class MemeEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=8, max_length=160)
    server_id: int = Field(gt=0)
    session_id: str | None = Field(default=None, min_length=36, max_length=36)
    source: MemeSource
    occurred_at: datetime
    moment_type: MomentType
    actor_player_ids: list[int] = Field(default_factory=list, max_length=3)
    target_player_ids: list[int] = Field(default_factory=list, max_length=3)
    game: MemeGameContext
    summary: str = Field(min_length=1, max_length=240)
    setup: str | None = Field(default=None, max_length=160)
    payoff: str | None = Field(default=None, max_length=160)
    importance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    facts: list[MemeFact] = Field(default_factory=list, max_length=8)

    @field_validator("actor_player_ids", "target_player_ids")
    @classmethod
    def unique_players(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("player ids must be unique")
        return value

    @field_validator("summary", "setup", "payoff")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("text cannot be blank")
        return normalized


class MemeGenerationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: MemeEventCreate
    preferred_formats: list[MemeFormat] = Field(default_factory=list, max_length=8)
    desired_harshness: int = Field(default=1, ge=0, le=2)


class MemeJobAccepted(BaseModel):
    job_id: str
    event_id: str
    status: str
    meme_worthy: bool
    meme_worthiness_score: float
    reasoning_code: str


class CaptionCandidateRead(BaseModel):
    id: str
    rank: int
    template_key: str
    template_version: int
    template_name: str
    category: str
    captions: dict[str, str]
    target_player_id: int | None
    lore_references: list[str]
    harshness: int
    quality_score: float


class MemeCandidateResponse(BaseModel):
    job_id: str
    status: str
    meme_worthy: bool
    meme_worthiness_score: float
    reasoning_code: str
    error_code: str | None
    candidates: list[CaptionCandidateRead]


class RenderMemeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: str = Field(min_length=36, max_length=36)
    template_key: str | None = Field(default=None, min_length=1, max_length=64)
    caption_overrides: dict[str, str] = Field(default_factory=dict)
    output_format: Literal["PNG"] = "PNG"

    @field_validator("caption_overrides")
    @classmethod
    def safe_overrides(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 2:
            raise ValueError("at most two caption zones can be overridden")
        return {str(key): " ".join(str(text).split()) for key, text in value.items()}


class GeneratedMemeRead(BaseModel):
    id: str
    job_id: str
    template_key: str
    template_name: str
    category: str
    captions: dict[str, str]
    target_player_id: int | None
    asset_url: str
    width: int
    height: int
    mime_type: str
    byte_size: int
    created_at: datetime


class MemeFeedbackCreate(BaseModel):
    feedback_type: Literal["FUNNY", "FORCED", "TOO_HARSH", "REPETITIVE", "WRONG_CONTEXT", "SAVE"]
    details: str | None = Field(default=None, max_length=500)


class MemeFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    meme_id: str
    user_id: int
    feedback_type: str
    details: str | None
    updated_at: datetime


class MemePreferenceUpdate(BaseModel):
    memes_enabled: bool = True
    allow_as_target: bool = True
    allow_lore_references: bool = True
    maximum_harshness: int = Field(default=1, ge=0, le=2)
    blocked_topics: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("blocked_topics")
    @classmethod
    def normalize_topics(cls, value: list[str]) -> list[str]:
        return sorted({" ".join(topic.split()).casefold()[:80] for topic in value if topic.strip()})


class MemePreferenceRead(MemePreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)
    server_id: int
    user_id: int
    updated_at: datetime


class MemeTemplateRead(BaseModel):
    key: str
    version: int
    name: str
    format: str
    categories: list[str]
    zones: list[dict[str, Any]]

