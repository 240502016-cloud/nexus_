from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

from app.platform.schemas import SeatedGameCreate

class EscapeCreate(SeatedGameCreate):
    """Üç mod: 3 insan · 2 insan + AI üçüncü konsol · 2 insan (AI yok).

    Koltuk sayısı hangi bulmaca setinin kullanılacağını belirler: üç koltukta
    NADİR-3 (üç rol), iki koltukta iki rollü set.
    """
    timer_mode: Literal["RELAXED", "STANDARD_45", "CHALLENGE_30"] = "RELAXED"; use_party_lore: bool = False

class EscapeAnswerCreate(BaseModel):
    answer: str = Field(min_length=1, max_length=160); action_token: str = Field(min_length=32, max_length=128); expected_revision: int = Field(ge=1)
class EscapeHintCreate(BaseModel):
    tier: int = Field(ge=1, le=4); action_token: str = Field(min_length=32, max_length=128); expected_revision: int = Field(ge=1)
class EscapeView(BaseModel):
    session_id: str; server_id: int; status: str; revision: int; rules_version: str; seat_count: int; timer_mode: str; elapsed_seconds: int; overtime: bool; nodes: list[dict]; players: list[dict]; ai_consoles: list[dict]; shared_inventory: list[str]; own_private: dict; hints: list[dict]; host_messages: list[dict]; result: dict | None; rng_commitment: str
class EscapeAttemptResponse(BaseModel):
    validator_result: str; node_id: str; view: EscapeView
