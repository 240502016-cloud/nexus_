from __future__ import annotations

from app.modules.meme_generator.schemas import MemeEventCreate
from app.modules.meme_generator.templates import BUILTIN_TEMPLATES, MemeTemplate


CATEGORY_BY_MOMENT = {
    "FAILURE": "REPEATED_FAILURE",
    "SUCCESS": "ACCIDENTAL_SUCCESS",
    "BETRAYAL": "BETRAYAL",
    "TEAM_EVENT": "TEAM_WIDE_FAILURE",
    "MILESTONE": "CLUTCH",
    "PREPARATION": "USELESS_PREPARATION",
    "NAVIGATION": "BAD_NAVIGATION",
    "PANIC": "PANIC",
    "SILENCE": "SILENT_DISASTER",
    "MANUAL_NOTE": "CURSED_PLAN",
}


def score_event(event: MemeEventCreate) -> tuple[float, str, str]:
    if event.confidence < 0.65:
        return 0.0, "LOW_CONFIDENCE", CATEGORY_BY_MOMENT[event.moment_type]
    if not event.actor_player_ids:
        return 0.0, "MISSING_ACTOR", CATEGORY_BY_MOMENT[event.moment_type]

    clarity = 1.0 if event.setup and event.payoff else 0.62
    surprise = 0.8 if event.moment_type in {"FAILURE", "SUCCESS", "BETRAYAL", "PANIC"} else 0.65
    specificity = min(1.0, 0.45 + len(event.facts) * 0.15 + (0.2 if len(event.summary) >= 35 else 0))
    visual = 0.7
    manual = 1.0 if event.source == "MANUAL" else 0.45
    positive = (
        0.28 * clarity
        + 0.22 * event.importance
        + 0.16 * surprise
        + 0.12 * specificity
        + 0.07 * visual
        + 0.05 * manual
    )
    score = round(max(0.0, min(1.0, positive)), 4)
    threshold = 0.55 if event.source == "MANUAL" else 0.62
    return score, "WORTHY" if score >= threshold else "NOT_WORTHY", CATEGORY_BY_MOMENT[event.moment_type]


def eligible_templates(
    *,
    category: str,
    preferred_formats: list[str],
) -> list[MemeTemplate]:
    result = [template for template in BUILTIN_TEMPLATES if category in template.categories]
    if preferred_formats:
        preferred = [template for template in result if template.format in preferred_formats]
        if preferred:
            result = preferred
    if not result:
        result = [BUILTIN_TEMPLATES[0]]
    return result[:3]

