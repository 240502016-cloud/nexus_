from __future__ import annotations

import copy
import hashlib
import hmac


ARCHETYPES = ["İz Sürücü", "Muhafız", "Arabulucu"]
TRAITS = [["kararlı", "meraklı"], ["sadık", "dikkatli"], ["sakin", "ikna edici"]]
AI_CHARACTER_NAME = "Yankı"
THEMES = {
    "MYSTERY": {"title": "Kayıp Fener", "goal": "Sönen fenerin sırrını çöz ve kıyı yolunu yeniden aç."},
    "SURVIVAL": {"title": "Kırık Ufuk", "goal": "Fırtına büyümeden sığınağı bul ve ekibi bir arada tut."},
    "FANTASY": {"title": "Üç Yol, Tek Kader", "goal": "Yankı Geçidi'ni uyandıran kaynağı bul ve kapıyı güvenle aç."},
}

SPOTLIGHT_CHOICES = [
    {"id": "INVESTIGATE", "label": "İzleri dikkatle araştır", "risk": "LOW", "effects": {"goal_progress": 1, "mystery_progress": 1, "threat": 0, "bond": 0}},
    {"id": "PROTECT", "label": "Grubu ve çevreyi güvene al", "risk": "LOW", "effects": {"goal_progress": 1, "mystery_progress": 0, "threat": -1, "bond": 1}},
    {"id": "PRESS_ON", "label": "Risk alıp hızla ilerle", "risk": "HIGH", "effects": {"goal_progress": 2, "mystery_progress": 0, "threat": 1, "bond": 0}},
]

JOINT_CHOICES = [
    {"id": "STABILIZE", "label": "Önce zemini sağlamlaştır", "effects": {"goal_progress": 1, "mystery_progress": 0, "threat": -1, "bond": 1}},
    {"id": "REVEAL_PATH", "label": "Gizli yolu açığa çıkar", "effects": {"goal_progress": 1, "mystery_progress": 2, "threat": 0, "bond": 0}},
    {"id": "PUSH_FORWARD", "label": "Tehdide rağmen ilerle", "effects": {"goal_progress": 2, "mystery_progress": 0, "threat": 1, "bond": 0}},
]


def initial_state(player_ids: list[int], *, ai_seats: list[int], theme: str, chapter_count: int, safety: dict) -> dict:
    """İnsanlar 0..n-1 koltuklarında, AI koltukları ``ai_seats`` içinde.

    AI karakterinin ``user_id`` değeri ``None``'dur — ``story_characters`` tablosuna
    satır yazılmaz, adı ve arketipi yalnız bu JSON durumunda yaşar.
    """
    meta = THEMES[theme]
    characters = [{"user_id": user_id, "seat": seat, "ai": False, "location": "Yankı Geçidi", "inventory": ["işaret taşı"], "actions_taken": 0} for seat, user_id in enumerate(player_ids)]
    characters += [{"user_id": None, "seat": seat, "ai": True, "name": AI_CHARACTER_NAME, "archetype": ARCHETYPES[seat], "traits": TRAITS[seat], "location": "Yankı Geçidi", "inventory": ["işaret taşı"], "actions_taken": 0} for seat in ai_seats]
    characters.sort(key=lambda item: item["seat"])
    return {"status": "ACTIVE", "title": meta["title"], "primary_goal": meta["goal"], "theme": theme, "chapter": 1, "chapter_count": chapter_count, "phase": "SPOTLIGHT", "spotlight_index": 0, "scene_number": 1, "threat": 2, "goal_progress": 0, "mystery_progress": 0, "bond": 0, "world_flags": [], "chapter_results": [], "characters": characters, "safety_envelope": safety, "ending_vector": None}


def seat_count(state: dict) -> int:
    return len(state["characters"])


def character_by_seat(state: dict, seat: int) -> dict:
    return next(item for item in state["characters"] if item["seat"] == seat)


def spotlight_order(state: dict) -> list[int]:
    """Bu bölümde sahnenin koltuk sırası. Her bölümde bir koltuk kayar."""
    total = seat_count(state)
    first = (state["chapter"] - 1) % total
    return [(first + offset) % total for offset in range(total)]


def active_seat(state: dict) -> int | None:
    if state["phase"] != "SPOTLIGHT" or state["status"] != "ACTIVE": return None
    return spotlight_order(state)[state["spotlight_index"]]


def active_user_id(state: dict) -> int | None:
    """Sahnedeki gerçek kullanıcı. Sıra AI'daysa veya faz SPOTLIGHT değilse ``None``."""
    seat = active_seat(state)
    if seat is None: return None
    return character_by_seat(state, seat)["user_id"]


def active_is_ai(state: dict) -> bool:
    seat = active_seat(state)
    return seat is not None and character_by_seat(state, seat)["ai"]


def legal_spotlight_choices(state: dict, user_id: int) -> list[dict]:
    if active_user_id(state) != user_id: return []
    return copy.deepcopy(SPOTLIGHT_CHOICES)


def _rng(seed: bytes, counter: int, purpose: str) -> tuple[int, int]:
    digest = hmac.new(seed, f"{counter}:{purpose}".encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:4], "big"), counter + 1


def _resolve_choice(state: dict, seat: int, choice: dict, seed: bytes, counter: int) -> tuple[dict, dict, int]:
    next_state = copy.deepcopy(state)
    random_value, counter = _rng(seed, counter, f"story:{state['chapter']}:{state['scene_number']}:{choice['id']}")
    if choice["risk"] == "HIGH":
        outcome = ["SUCCESS", "SUCCESS_WITH_COST", "FAIL_FORWARD"][random_value % 3]
    else:
        outcome = "SUCCESS" if random_value % 4 else "SUCCESS_WITH_COST"
    effects = dict(choice["effects"])
    if outcome == "SUCCESS_WITH_COST": effects["threat"] += 1
    if outcome == "FAIL_FORWARD": effects["goal_progress"] = max(1, effects["goal_progress"] - 1); effects["threat"] += 1
    _apply_effects(next_state, effects)
    character = character_by_seat(next_state, seat); character["actions_taken"] += 1
    result = {"kind": choice["id"], "label": choice["label"], "outcome": outcome, "effects": effects, "actor_user_id": character["user_id"], "actor_seat": seat, "actor_is_ai": character["ai"], "chapter": state["chapter"], "scene_number": state["scene_number"]}
    next_state["spotlight_index"] += 1; next_state["scene_number"] += 1
    if next_state["spotlight_index"] >= seat_count(next_state): next_state["phase"] = "JOINT_VOTE"
    return next_state, result, counter


def apply_spotlight(state: dict, user_id: int, action_id: str, seed: bytes, counter: int) -> tuple[dict, dict, int]:
    choice = next((item for item in legal_spotlight_choices(state, user_id) if item["id"] == action_id), None)
    if not choice: raise ValueError("ILLEGAL_ACTION")
    return _resolve_choice(state, active_seat(state), choice, seed, counter)


def ai_spotlight_choice(state: dict, seed: bytes, counter: int) -> tuple[dict, int]:
    """AI koltuğunun sahne kararı — deterministik, tohumdan türetilir.

    Karar LLM'e sorulmaz: AI Gateway kapalıyken oyunun kilitlenmemesi gerekir
    (yalnız anlatım metni modelden gelir). Aynı tohum aynı kararı verir, bu da
    ``rng_commitment`` doğrulanabilirliğini korur.
    """
    remaining = state["chapter_count"] - state["chapter"] + 1
    pace = state["chapter_count"] * (seat_count(state) + 1)
    behind = state["goal_progress"] < pace - remaining * (seat_count(state) + 1) // 2
    if state["threat"] >= 4:
        pick = "PROTECT"
    elif behind:
        pick = "PRESS_ON"
    else:
        random_value, counter = _rng(seed, counter, f"story-ai:{state['chapter']}:{state['scene_number']}")
        pick = "INVESTIGATE" if random_value % 3 else "PROTECT"
    return next(item for item in SPOTLIGHT_CHOICES if item["id"] == pick), counter


def apply_ai_spotlight(state: dict, seed: bytes, counter: int) -> tuple[dict, dict, int]:
    seat = active_seat(state)
    if seat is None or not character_by_seat(state, seat)["ai"]: raise ValueError("NOT_AI_TURN")
    choice, counter = ai_spotlight_choice(state, seed, counter)
    return _resolve_choice(state, seat, copy.deepcopy(choice), seed, counter)


def ai_joint_choice(state: dict, seed: bytes, counter: int) -> tuple[str, int]:
    """AI koltuğunun bölüm sonu ortak oyu — aynı gerekçeyle deterministik."""
    if state["threat"] >= 4: return "STABILIZE", counter
    if state["mystery_progress"] < state["chapter"]: return "REVEAL_PATH", counter
    random_value, counter = _rng(seed, counter, f"story-ai-joint:{state['chapter']}")
    return ("PUSH_FORWARD" if random_value % 2 else "STABILIZE"), counter


def _apply_effects(state: dict, effects: dict) -> None:
    state["goal_progress"] = min(12, max(0, state["goal_progress"] + effects["goal_progress"]))
    state["mystery_progress"] = min(8, max(0, state["mystery_progress"] + effects["mystery_progress"]))
    state["threat"] = min(6, max(0, state["threat"] + effects["threat"]))
    state["bond"] = min(6, max(-3, state["bond"] + effects["bond"]))


def resolve_joint(state: dict, choice_id: str) -> tuple[dict, dict]:
    choice = next(item for item in JOINT_CHOICES if item["id"] == choice_id)
    next_state = copy.deepcopy(state); _apply_effects(next_state, choice["effects"])
    result = {"chapter": state["chapter"], "choice_id": choice_id, "label": choice["label"], "effects": choice["effects"]}
    next_state["chapter_results"] = [*next_state["chapter_results"], result]
    if state["chapter"] >= state["chapter_count"]:
        # Eşikler koltuk sayısına göre ölçeklenir: her bölümde koltuk başına bir sahne
        # artı bir ortak karar ilerleme üretir. Üç koltukta bu eskisiyle birebir aynı
        # değerleri verir (goal: chapter_count*4, mystery: chapter_count*2); iki koltukta
        # sahne sayısı azaldığı için eşik de düşer, yoksa iyi son imkânsız hâle gelirdi.
        seats = seat_count(next_state)
        goal_target = state["chapter_count"] * (seats + 1)
        mystery_target = (state["chapter_count"] * seats * 2) // 3
        next_state["status"] = "COMPLETED"; next_state["phase"] = "COMPLETED"
        next_state["ending_vector"] = {"primary_goal": "RESOLVED" if next_state["goal_progress"] >= goal_target else "FAILED_FORWARD", "threat": "LOW" if next_state["threat"] <= 2 else "MEDIUM" if next_state["threat"] <= 4 else "HIGH", "relationships": "UNITED" if next_state["bond"] >= 2 else "COMPLEX", "mystery": "RESOLVED" if next_state["mystery_progress"] >= mystery_target else "PARTIAL"}
    else:
        next_state["chapter"] += 1; next_state["phase"] = "SPOTLIGHT"; next_state["spotlight_index"] = 0; next_state["scene_number"] += 1
    return next_state, result
