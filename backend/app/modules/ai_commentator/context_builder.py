from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.models import User
from app.modules.ai_commentator.models import (
    CommentatorEvent,
    CommentatorSessionPlayer,
    GeneratedCommentary,
)
from app.modules.ai_commentator.profiles import get_profile
from app.modules.party_lore.models import LoreUsage
from app.modules.party_lore.service import find_entries
from app.platform.models import ExperienceSession, utcnow


def build_commentary_context(
    db: Session,
    *,
    session: ExperienceSession,
    event: CommentatorEvent,
    actor: User,
) -> tuple[dict, dict[str, object]]:
    settings = session.settings or {}
    profile = get_profile(str(settings.get("profile_key", "dry_sarcastic")))
    if not profile:
        raise ValueError("Commentator profile is not available")

    session_preferences = {
        row.user_id: row
        for row in db.query(CommentatorSessionPlayer)
        .filter(CommentatorSessionPlayer.session_id == session.id)
        .all()
    }
    users = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(session_preferences.keys())).all()
    }
    players: list[dict] = []
    allowed_targets: list[int] = []
    blocked_topics: set[str] = set()
    for user_id, row in sorted(session_preferences.items()):
        preference = row.preference_snapshot or {}
        user = users[user_id]
        players.append(
            {
                "id": user_id,
                "displayName": user.display_name or user.username,
                "commentaryEnabled": preference.get("commentary_enabled", True),
                "allowTargetedJokes": preference.get("allow_targeted_jokes", True),
                "allowLoreReferences": preference.get("allow_lore_references", True),
                "maximumHarshness": preference.get("maximum_harshness", 1),
                "preferredHumorStyles": preference.get("preferred_humor_styles", ["GENTLE"]),
            }
        )
        blocked_topics.update(preference.get("blocked_topics", []))
        if (
            preference.get("commentary_enabled", True)
            and preference.get("allow_targeted_jokes", True)
            and preference.get("maximum_harshness", 1) >= profile["harshness"]
        ):
            allowed_targets.append(user_id)

    recent_lore_ids = {
        row[0]
        for row in db.query(LoreUsage.lore_id)
        .filter(
            LoreUsage.server_id == session.server_id,
            LoreUsage.module == "ai_commentator",
            LoreUsage.created_at >= utcnow() - timedelta(days=7),
        )
        .all()
    }
    lore = find_entries(
        db,
        server_id=session.server_id,
        actor=actor,
        module="ai_commentator",
        query=event.normalized_summary,
        participant_ids=event.actor_player_ids + event.target_player_ids,
        limit=2,
        excluded_lore_ids=recent_lore_ids,
    )
    lore = [
        entry
        for entry in lore
        if all(
            session_preferences.get(participant.user_id)
            and session_preferences[participant.user_id].preference_snapshot.get(
                "allow_lore_references", True
            )
            for participant in entry.participants
        )
    ]

    recent = (
        db.query(GeneratedCommentary)
        .filter(
            GeneratedCommentary.session_id == session.id,
            GeneratedCommentary.dispatch_state == "delivered",
        )
        .order_by(GeneratedCommentary.created_at.desc())
        .limit(8)
        .all()
    )
    target_counts = {user_id: row.targeted_count for user_id, row in session_preferences.items()}
    context = {
        "session": {
            "id": session.id,
            "gameKey": settings.get("game_key", "manual"),
            "intensity": settings.get("intensity", "NORMAL"),
            "currentTone": settings.get("current_tone", "UNKNOWN"),
        },
        "commentatorProfile": {
            "key": profile["key"],
            "style": profile["style"],
            "harshness": profile["harshness"],
            "enabledTones": profile["tones"],
        },
        "players": players,
        "allowedPartyLore": [
            {"loreId": entry.id, "title": entry.title, "summary": entry.summary}
            for entry in lore
        ],
        "recentCommentary": [item.commentary_text for item in reversed(recent)],
        "recentTargetCounts": target_counts,
        "currentEvent": {
            "eventId": event.external_event_id,
            "category": event.category,
            "actorPlayerIds": event.actor_player_ids,
            "targetPlayerIds": event.target_player_ids,
            "summary": event.normalized_summary,
            "importance": event.importance,
            "confidence": event.source_confidence,
            "game": event.game_context,
            "attributes": event.normalized_attributes,
        },
        "targetingPolicy": {"allowedTargetPlayerIds": allowed_targets},
        "outputLimits": {"maxChars": profile["max_chars"], "maxSentences": 1},
    }
    policy: dict[str, object] = {
        "allowed_target_ids": set(allowed_targets),
        "allowed_lore_ids": {entry.id for entry in lore},
        "blocked_topics": blocked_topics,
        "max_chars": profile["max_chars"],
        "profile": profile,
        "recent_texts": [item.commentary_text or "" for item in recent],
    }
    return context, policy
