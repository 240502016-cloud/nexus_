from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.platform.schemas import SeatedGameCreate


class StorySafetyUpdate(BaseModel):
    horror_level: int = Field(default=1, ge=0, le=3)
    violence_level: int = Field(default=1, ge=0, le=3)
    romance: Literal["OFF", "SOFT", "FADE_TO_BLACK"] = "OFF"
    player_conflict: Literal["COOPERATIVE", "CONTROLLED"] = "COOPERATIVE"
    betrayal: Literal["OFF", "NPC_ONLY"] = "OFF"
    personal_jokes: bool = False
    dark_humor: bool = False


class StoryCreate(SeatedGameCreate):
    theme: Literal["MYSTERY", "SURVIVAL", "FANTASY"] = "FANTASY"
    length: Literal["SHORT", "STANDARD", "LONG"] = "SHORT"
    use_party_lore: bool = False


class StoryActionCreate(BaseModel):
    action_id: Literal["INVESTIGATE", "PROTECT", "PRESS_ON"]
    action_token: str = Field(min_length=32, max_length=128)
    expected_revision: int = Field(ge=1)


class StoryVoteCreate(BaseModel):
    choice_id: Literal["STABILIZE", "REVEAL_PATH", "PUSH_FORWARD"]
    action_token: str = Field(min_length=32, max_length=128)
    expected_revision: int = Field(ge=1)


class StoryView(BaseModel):
    session_id: str
    server_id: int
    status: str
    revision: int
    title: str
    primary_goal: str
    theme: str
    chapter: int
    chapter_count: int
    phase: str
    active_user_id: int | None
    active_seat: int | None
    active_is_ai: bool
    seat_count: int
    scene_number: int
    threat: int
    goal_progress: int
    mystery_progress: int
    bond: int
    characters: list[dict]
    safety_envelope: dict
    spotlight_choices: list[dict]
    joint_choices: list[dict]
    submitted_vote_count: int
    own_vote: str | None
    action_token: str | None
    chapter_results: list[dict]
    ending_vector: dict | None
    prose: list[dict]
    rng_commitment: str
