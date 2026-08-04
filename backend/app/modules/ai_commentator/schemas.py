from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Intensity = Literal["LOW", "NORMAL", "HIGH"]
SessionTone = Literal["CALM", "FOCUSED", "PLAYFUL", "TENSE", "UPSET", "UNKNOWN"]
EventSource = Literal["MANUAL", "DISCORD", "GAME_CONNECTOR", "TRANSCRIPT"]
EventCategory = Literal[
    "PLAYER_DEATH",
    "PLAYER_FAIL",
    "CLUTCH",
    "BETRAYAL",
    "TEAMWORK",
    "ACCIDENTAL_SUCCESS",
    "REPEATED_MISTAKE",
    "SILENCE",
    "ARGUMENT",
    "MILESTONE",
    "MANUAL_NOTE",
]


class CommentarySessionCreate(BaseModel):
    game_key: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    player_ids: list[int] = Field(min_length=3, max_length=3)
    profile_key: str = Field(default="dry_sarcastic", min_length=1, max_length=64)
    intensity: Intensity = "NORMAL"
    text_to_speech_enabled: bool = False
    output_channel_id: int | None = Field(default=None, gt=0)

    @field_validator("player_ids")
    @classmethod
    def exactly_three_unique_players(cls, value: list[int]) -> list[int]:
        if len(set(value)) != 3:
            raise ValueError("player_ids must contain three unique users")
        return value


class CommentarySessionUpdate(BaseModel):
    expected_revision: int = Field(ge=0)
    profile_key: str | None = Field(default=None, min_length=1, max_length=64)
    intensity: Intensity | None = None
    silent_mode: bool | None = None
    current_tone: SessionTone | None = None
    text_to_speech_enabled: bool | None = None


class CommentarySessionEnd(BaseModel):
    expected_revision: int = Field(ge=0)


class CommentarySessionRead(BaseModel):
    id: str
    server_id: int
    game_key: str
    player_ids: list[int]
    profile_key: str
    intensity: Intensity
    silent_mode: bool
    text_to_speech_enabled: bool
    current_tone: SessionTone
    status: str
    revision: int
    output_channel_id: int | None
    started_at: datetime
    ended_at: datetime | None


class GameContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_key: str = Field(min_length=1, max_length=80)
    match_id: str | None = Field(default=None, max_length=160)
    round_id: str | None = Field(default=None, max_length=160)
    mode: str | None = Field(default=None, max_length=80)
    map: str | None = Field(default=None, max_length=80)


class CommentatorEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=8, max_length=160)
    source: EventSource
    occurred_at: datetime
    category: EventCategory
    actor_player_ids: list[int] = Field(default_factory=list, max_length=3)
    target_player_ids: list[int] = Field(default_factory=list, max_length=3)
    game: GameContext
    importance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    summary: str = Field(min_length=1, max_length=240)
    emotional_tone: SessionTone | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("actor_player_ids", "target_player_ids")
    @classmethod
    def unique_players(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("player ids must be unique")
        return value

    @field_validator("summary")
    @classmethod
    def normalized_summary(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("summary cannot be blank")
        return normalized


class CommentatorEventRead(BaseModel):
    id: str
    event_id: str
    category: str
    summary: str
    occurred_at: datetime
    trigger_score: float
    trigger_decision: str
    processing_state: str


class PostEventResponse(BaseModel):
    event_id: str
    accepted: bool = True
    state: Literal["PENDING", "DEDUPLICATED", "FILTERED"]


class GeneratedCommentaryRead(BaseModel):
    id: str
    session_id: str
    source_event_ids: list[str]
    should_comment: bool
    commentary: str | None
    target_player_id: int | None
    tone: str | None
    lore_references: list[str]
    confidence: float
    reason_code: str
    dispatch_state: str
    created_at: datetime
    delivered_at: datetime | None


class CommentaryHistoryRead(BaseModel):
    session: CommentarySessionRead
    events: list[CommentatorEventRead]
    commentary: list[GeneratedCommentaryRead]


class CommentaryFeedbackCreate(BaseModel):
    feedback_type: Literal["FUNNY", "NOT_FUNNY", "TOO_HARSH", "REPETITIVE", "WRONG_CONTEXT"]
    details: str | None = Field(default=None, max_length=500)


class CommentaryFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    commentary_id: str
    user_id: int
    feedback_type: str
    details: str | None
    updated_at: datetime


class CommentatorPreferenceUpdate(BaseModel):
    commentary_enabled: bool = True
    allow_targeted_jokes: bool = True
    allow_lore_references: bool = True
    maximum_harshness: int = Field(default=1, ge=0, le=3)
    preferred_humor_styles: list[
        Literal["DRY", "ABSURD", "HYPE", "ANALYTICAL", "GENTLE"]
    ] = Field(default_factory=lambda: ["GENTLE"], max_length=5)
    blocked_topics: list[str] = Field(default_factory=list, max_length=20)
    tts_enabled: bool = True

    @field_validator("blocked_topics")
    @classmethod
    def normalize_topics(cls, value: list[str]) -> list[str]:
        cleaned = sorted({" ".join(topic.split()).casefold()[:80] for topic in value if topic.strip()})
        return cleaned


class CommentatorPreferenceRead(CommentatorPreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)

    server_id: int
    user_id: int
    updated_at: datetime


class CommentatorProfileRead(BaseModel):
    key: str
    name: str
    description: str
    max_chars: int
    harshness: int
    lore_probability: float
    tones: list[str]
