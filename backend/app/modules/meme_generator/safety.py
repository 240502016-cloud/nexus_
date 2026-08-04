from __future__ import annotations

import re


# MVP keeps profanity disabled and blocks direct person-level degradation. This
# deliberately complements, rather than replaces, per-player blocked topics.
HARD_BLOCKED_TOKENS = {
    "aptal",
    "beceriksiz",
    "değersiz",
    "gerizekalı",
    "mal",
    "salak",
    "sürtük",
    "orospu",
    "piç",
}


def contains_hard_blocked_text(value: str) -> bool:
    tokens = set(re.findall(r"\w+", value.casefold()))
    return bool(tokens.intersection(HARD_BLOCKED_TOKENS))

