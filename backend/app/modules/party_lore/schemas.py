from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LoreCandidateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=2000)
    participant_ids: list[int] = Field(min_length=1, max_length=32)
    category: str = Field(default="moment", min_length=1, max_length=32)
    sensitivity: str = Field(default="low")
    allowed_modules: list[str] = Field(min_length=1, max_length=8)

    @field_validator("participant_ids")
    @classmethod
    def unique_participants(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("participant_ids must be unique")
        return value

    @field_validator("title", "summary", "category")
    @classmethod
    def non_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value


class LoreParticipantDecisionRead(BaseModel):
    user_id: int
    decision: str
    decided_at: datetime | None


class LoreCandidateRead(BaseModel):
    id: str
    server_id: int
    submitted_by_id: int
    title: str
    summary: str
    category: str
    sensitivity: str
    allowed_modules: list[str]
    status: str
    participants: list[LoreParticipantDecisionRead]
    lore_id: str | None
    created_at: datetime
    reviewed_at: datetime | None


class LoreReview(BaseModel):
    decision: str


class LoreEntryRead(BaseModel):
    id: str
    server_id: int
    title: str
    summary: str
    category: str
    sensitivity: str
    allowed_modules: list[str]
    participant_ids: list[int]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class LoreRetrieve(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    module: str = Field(min_length=1, max_length=32)
    query: str = Field(default="", max_length=500)
    participant_ids: list[int] = Field(default_factory=list, max_length=32)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("participant_ids")
    @classmethod
    def unique_filter_participants(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("participant_ids must be unique")
        return value


class LoreRetrieveResult(BaseModel):
    items: list[LoreEntryRead]
    request_id: str
