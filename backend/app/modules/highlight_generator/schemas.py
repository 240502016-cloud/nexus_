from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecordingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: Literal["MANUAL_UPLOAD", "OBS_REPLAY_BUFFER"] = "MANUAL_UPLOAD"
    original_filename: str = Field(min_length=1, max_length=180)
    byte_size: int = Field(ge=1, le=1024 * 1024 * 1024)
    content_type: Literal["video/mp4", "video/x-matroska"]
    session_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("original_filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        name = value.replace("\\", "/").split("/")[-1].strip()
        if not name or name in {".", ".."}:
            raise ValueError("invalid filename")
        return name


class RecordingRead(BaseModel):
    id: str
    server_id: int
    session_id: str | None
    source_type: str
    original_filename: str
    status: str
    upload_url: str | None = None
    byte_size: int | None
    duration_ms: int | None
    width: int | None
    height: int | None
    has_audio: bool | None
    error_code: str | None
    created_at: datetime


class MarkerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    marker_id: str = Field(min_length=8, max_length=160)
    source: Literal["MANUAL", "COMMENTATOR", "GAME_TELEMETRY"] = "MANUAL"
    offset_ms: int = Field(ge=0)
    category_hint: Literal["SKILL", "COMEDY", "FAILURE", "CHAOS", "LORE_WORTHY"] | None = None
    participant_player_ids: list[int] = Field(min_length=1, max_length=3)
    summary: str | None = Field(default=None, max_length=500)
    manual_priority: int = Field(default=1, ge=0, le=1)
    commentator_priority: float | None = Field(default=None, ge=0, le=1)
    game_event_severity: float | None = Field(default=None, ge=0, le=1)

    @field_validator("participant_player_ids")
    @classmethod
    def unique_players(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("player ids must be unique")
        return value


class CandidateRead(BaseModel):
    id: str
    recording_id: str
    marker_id: str
    start_ms: int
    end_ms: int
    anchor_ms: int
    score: float
    primary_category: str
    title: str
    description: str
    participant_player_ids: list[int]
    status: str


class RenderHighlightCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    title_override: str | None = Field(default=None, min_length=1, max_length=120)
    description_override: str | None = Field(default=None, max_length=300)
    variant: Literal["LANDSCAPE"] = "LANDSCAPE"


class RenderedHighlightRead(BaseModel):
    id: str
    candidate_id: str
    status: str
    category: str
    variant: str
    title: str
    description: str
    video_url: str | None
    thumbnail_url: str | None
    duration_ms: int
    width: int | None
    height: int | None
    error_code: str | None
    created_at: datetime


class HighlightFeedbackCreate(BaseModel):
    feedback_type: Literal["GOOD", "WRONG_MOMENT", "TRIM_EARLIER", "TRIM_LATER", "TOO_LONG", "SAVE"]
    details: str | None = Field(default=None, max_length=500)

