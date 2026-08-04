from __future__ import annotations

from dataclasses import dataclass


CATEGORY_VALUE = {
    "MILESTONE": 0.92,
    "CLUTCH": 0.90,
    "BETRAYAL": 0.82,
    "REPEATED_MISTAKE": 0.80,
    "TEAMWORK": 0.77,
    "ACCIDENTAL_SUCCESS": 0.74,
    "MANUAL_NOTE": 0.70,
    "PLAYER_DEATH": 0.58,
    "PLAYER_FAIL": 0.54,
    "SILENCE": 0.32,
    "ARGUMENT": 0.0,
}
INTENSITY_THRESHOLD = {"LOW": 0.76, "NORMAL": 0.64, "HIGH": 0.52}


@dataclass(frozen=True)
class TriggerResult:
    score: float
    decision: str


def decide_trigger(
    *,
    category: str,
    importance: float,
    source_confidence: float,
    source: str,
    intensity: str,
    session_tone: str,
    silent_mode: bool,
    commentary_enabled: bool,
    duplicate: bool = False,
    cooldown_active: bool = False,
    novelty: float = 0.5,
    lore_relevance: float = 0.0,
    recent_frequency: float = 0.0,
    target_saturation: float = 0.0,
) -> TriggerResult:
    """Pure deterministic gate; most events never reach an LLM."""
    if duplicate:
        return TriggerResult(0.0, "SUPERSEDED")
    if silent_mode:
        return TriggerResult(0.0, "SILENT_MODE")
    if not commentary_enabled:
        return TriggerResult(0.0, "SAFETY")
    if source_confidence < 0.55:
        return TriggerResult(0.0, "BELOW_THRESHOLD")
    if category == "ARGUMENT" or session_tone in {"TENSE", "UPSET"}:
        return TriggerResult(0.0, "SAFETY")
    if cooldown_active:
        return TriggerResult(0.0, "COOLDOWN")

    category_value = CATEGORY_VALUE.get(category, 0.0)
    emotional_fit = 1.0 if session_tone in {"CALM", "FOCUSED", "PLAYFUL", "UNKNOWN"} else 0.0
    manual_bonus = 1.0 if source == "MANUAL" else 0.0
    positive = (
        0.28 * importance
        + 0.18 * novelty
        + 0.14 * category_value
        + 0.12 * source_confidence
        + 0.10 * lore_relevance
        + 0.08
        + 0.05 * emotional_fit
        + 0.05 * manual_bonus
    )
    penalty = 0.20 * recent_frequency + 0.18 * target_saturation
    score = max(0.0, min(1.0, positive - penalty))
    threshold = INTENSITY_THRESHOLD.get(intensity, INTENSITY_THRESHOLD["NORMAL"])
    return TriggerResult(round(score, 4), "GENERATE" if score >= threshold else "BELOW_THRESHOLD")
