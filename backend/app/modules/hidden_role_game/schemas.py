from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.platform.schemas import SeatedGameCreate


class HiddenGameCreate(SeatedGameCreate):
    pass


class ClaimCreate(BaseModel):
    subject_option_id: Literal["A", "B", "C"]
    proposition: Literal["SUPPORTS_SAFE", "EXCLUDES_SAFE", "RISK_HIGH", "RISK_LOW"]
    flavor_text: str = Field(default="", max_length=240)
    action_token: str = Field(min_length=32, max_length=128)
    expected_revision: int = Field(ge=1)


class VoteCreate(BaseModel):
    option_id: Literal["A", "B", "C"]
    action_token: str = Field(min_length=32, max_length=128)
    expected_revision: int = Field(ge=1)


class DeductionCreate(BaseModel):
    # Anahtarlar katılımcı anahtarıdır: insan koltuğu için kullanıcı kimliği ("12"),
    # AI koltuğu için "ai:<koltuk>". Oyuncu kimliği int olmadığı için sözlük str anahtarlıdır.
    office_by_key: dict[str, Literal["SENTINEL", "ARCHIVIST", "ENVOY"]]
    mandate_by_key: dict[str, Literal["SEAL", "REVEAL", "REDIRECT"]]
    action_token: str = Field(min_length=32, max_length=128)
    expected_revision: int = Field(ge=1)


class HiddenGameView(BaseModel):
    session_id: str
    server_id: int
    status: str
    revision: int
    round: int
    phase: str
    stability: int
    crisis: dict | None
    players: list[dict]
    human_player_count: int
    claims: list[dict]
    submitted_vote_count: int
    submitted_deduction_count: int
    round_results: list[dict]
    own_private: dict
    legal_action: dict | None
    result: dict | None
    recap: str | None
    rng_commitment: str
