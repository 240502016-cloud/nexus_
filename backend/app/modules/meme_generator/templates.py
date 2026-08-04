from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaptionZone:
    key: str
    max_chars: int
    max_lines: int


@dataclass(frozen=True)
class MemeTemplate:
    key: str
    version: int
    name: str
    format: str
    categories: tuple[str, ...]
    zones: tuple[CaptionZone, ...]
    background: tuple[int, int, int]
    accent: tuple[int, int, int]
    cooldown_hours: int = 168


def _two_zone(
    key: str,
    name: str,
    categories: tuple[str, ...],
    background: tuple[int, int, int],
    accent: tuple[int, int, int],
    *,
    format: str = "TEXT_CARD",
    cooldown_hours: int = 168,
) -> MemeTemplate:
    return MemeTemplate(
        key=key,
        version=1,
        name=name,
        format=format,
        categories=categories,
        zones=(CaptionZone("TITLE", 48, 2), CaptionZone("SUBTITLE", 72, 3)),
        background=background,
        accent=accent,
        cooldown_hours=cooldown_hours,
    )


# These originals are rendered from shapes and text, so the MVP has no hidden
# network dependency or third-party image copyright ambiguity.
BUILTIN_TEMPLATES: tuple[MemeTemplate, ...] = (
    _two_zone("expectation_reality", "Beklenti / Gerçeklik", ("OVERCONFIDENT_FAILURE", "USELESS_PREPARATION", "CURSED_PLAN"), (20, 24, 39), (245, 158, 11), format="EXPECTATION_REALITY", cooldown_hours=336),
    _two_zone("achievement_unlocked", "Başarım Açıldı", ("ACCIDENTAL_SUCCESS", "CLUTCH", "IMPOSSIBLE_COMEBACK", "AFK_TIMING"), (18, 43, 36), (52, 211, 153), format="ACHIEVEMENT_CARD"),
    _two_zone("patch_notes", "Yama Notları", ("FAKE_EXPERT", "CURSED_PLAN", "BETRAYAL"), (31, 34, 50), (139, 92, 246), format="PATCH_NOTES"),
    _two_zone("breaking_news", "Son Dakika", ("BETRAYAL", "GREED_PUNISHED", "PREMATURE_CELEBRATION", "IMPOSSIBLE_COMEBACK"), (54, 20, 25), (239, 68, 68), format="NEWS_REPORT"),
    _two_zone("player_stats", "Oyuncu İstatistiği", ("REPEATED_FAILURE", "BAD_NAVIGATION", "RESOURCE_HOARDER", "AFK_TIMING"), (17, 35, 54), (56, 189, 248), format="PLAYER_STATS", cooldown_hours=336),
    _two_zone("incident_report", "Olay Raporu", ("FRIENDLY_FIRE", "TEAM_WIDE_FAILURE", "BLAMING_LAG"), (42, 32, 18), (251, 191, 36), format="TEXT_CARD"),
    _two_zone("panic_button", "Panik Protokolü", ("PANIC", "SILENT_DISASTER"), (42, 17, 38), (236, 72, 153), format="REACTION_CARD"),
    _two_zone("team_sync", "Takım Senkronu", ("TEAM_WIDE_FAILURE", "SILENT_DISASTER", "CURSED_PLAN"), (18, 37, 45), (34, 211, 238), format="REACTION_CARD"),
    _two_zone("obvious_clue", "Kadrajın Başrolü", ("MISSED_OBVIOUS", "BAD_NAVIGATION"), (31, 25, 48), (167, 139, 250), format="CAPTIONED_TEMPLATE", cooldown_hours=336),
    _two_zone("loot_economy", "Envanter Ekonomisi", ("GREED_PUNISHED", "RESOURCE_HOARDER", "USELESS_PREPARATION"), (21, 40, 29), (74, 222, 128), format="PLAYER_STATS"),
)

TEMPLATES_BY_KEY = {template.key: template for template in BUILTIN_TEMPLATES}


def public_template(template: MemeTemplate) -> dict:
    return {
        "key": template.key,
        "version": template.version,
        "name": template.name,
        "format": template.format,
        "categories": list(template.categories),
        "zones": [
            {"key": zone.key, "max_chars": zone.max_chars, "max_lines": zone.max_lines}
            for zone in template.zones
        ],
    }

