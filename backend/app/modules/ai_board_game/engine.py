from __future__ import annotations

import copy
import hashlib
import hmac


RULES_VERSION = "last-portal-v1"
MAX_ROUNDS = 8
# AI'ın oturduğu koltuğun tahtadaki adı.
AI_PLAYER_NAME = "Gezgin"

TILES = {
    "E0": {"label": "Köz Kampı", "type": "CAMP", "region": "EMBER", "adjacent": ["E1", "G3", "P"]},
    "E1": {"label": "Köz Hurdalığı", "type": "SALVAGE", "region": "EMBER", "adjacent": ["E0", "E2"]},
    "E2": {"label": "Köz Sınavı", "type": "TRIAL", "region": "EMBER", "adjacent": ["E1", "E3"], "sigil": "EMBER_SIGIL"},
    "E3": {"label": "Köz Kavşağı", "type": "CROSSROADS", "region": "EMBER", "adjacent": ["E2", "T0"]},
    "T0": {"label": "Gelgit Kampı", "type": "CAMP", "region": "TIDE", "adjacent": ["E3", "T1", "P"]},
    "T1": {"label": "Gelgit Hurdalığı", "type": "SALVAGE", "region": "TIDE", "adjacent": ["T0", "T2"]},
    "T2": {"label": "Gelgit Sınavı", "type": "TRIAL", "region": "TIDE", "adjacent": ["T1", "T3"], "sigil": "TIDE_SIGIL"},
    "T3": {"label": "Gelgit Kavşağı", "type": "CROSSROADS", "region": "TIDE", "adjacent": ["T2", "G0"]},
    "G0": {"label": "Koru Kampı", "type": "CAMP", "region": "GROVE", "adjacent": ["T3", "G1", "P"]},
    "G1": {"label": "Koru Hurdalığı", "type": "SALVAGE", "region": "GROVE", "adjacent": ["G0", "G2"]},
    "G2": {"label": "Koru Sınavı", "type": "TRIAL", "region": "GROVE", "adjacent": ["G1", "G3"], "sigil": "GROVE_SIGIL"},
    "G3": {"label": "Koru Kavşağı", "type": "CROSSROADS", "region": "GROVE", "adjacent": ["G2", "E0"]},
    "P": {"label": "Son Portal", "type": "PORTAL", "region": "CENTER", "adjacent": ["E0", "T0", "G0"]},
}


STARTS = ["E0", "T0", "G0"]


def action_points_for(seat_total: int) -> int:
    """Tur başına aksiyon puanı.

    Üç koltukta 2 AP'dir. İki koltukta tur başına bir oyuncu eksik olduğu için
    oyunun toplam aksiyon bütçesi üçte bir azalır; portalı açmak için gereken üç
    mühür ve üç şarj ise değişmez. Ölçüldüğünde iki oyuncunun görevi tamamlaması
    ~30 AP istiyor, 2 AP ile toplam bütçe 32 AP'ye düşüyordu — başarısız bir sınav
    ya da bir hurda toplama turu oyunu matematiksel olarak kaybettiriyordu.
    3 AP toplam bütçeyi 48'de, yani üç kişilik oyunla aynı yerde tutar.
    """
    return 3 if seat_total == 2 else 2


def initial_state(player_ids: list[int], *, ai_seats: list[int] | None = None) -> dict:
    ai_seats = ai_seats or []
    seats = [(seat, user_id, False) for seat, user_id in enumerate(player_ids)]
    seats += [(seat, None, True) for seat in ai_seats]
    seats.sort(key=lambda item: item[0])
    players = [
        {
            "user_id": user_id,
            "seat": seat,
            "ai": is_ai,
            "tile_id": STARTS[seat],
            "energy": 3,
            "scrap": 1,
            "fame": 0,
            "shield": 0,
            "momentum": 0,
            "sigils": [],
            "contribution": 0,
        }
        for seat, user_id, is_ai in seats
    ]
    return {
        "rules_version": RULES_VERSION,
        "status": "ACTIVE",
        "round": 1,
        "maximum_rounds": MAX_ROUNDS,
        "active_seat": 0,
        "turn_index": 0,
        "action_points": action_points_for(len(players)),
        "chaos": 2,
        "chaos_limit": 12,
        "portal_charge": 0,
        "deposited_sigils": [],
        "claimed_sigils": {},
        "players": players,
        "round_flags": {"scavenged": [], "attempted_trials": []},
        "group_outcome": None,
        "winner_user_id": None,
        "end_reason": None,
        "rng_seed_reveal": None,
    }


def _player(state: dict, user_id: int) -> dict:
    return next(item for item in state["players"] if item["user_id"] == user_id)


def player_by_seat(state: dict, seat: int) -> dict:
    return next(item for item in state["players"] if item["seat"] == seat)


def seat_count(state: dict) -> int:
    return len(state["players"])


def active_user_id(state: dict) -> int | None:
    """Sırası gelen gerçek kullanıcı; koltuk AI'daysa ``None``."""
    return player_by_seat(state, state["active_seat"])["user_id"]


def active_is_ai(state: dict) -> bool:
    return state["status"] == "ACTIVE" and player_by_seat(state, state["active_seat"])["ai"]


def legal_action_specs(state: dict, user_id: int) -> list[dict]:
    if state["status"] != "ACTIVE" or active_user_id(state) != user_id:
        return []
    return _actions_for(state, _player(state, user_id))


def _actions_for(state: dict, player: dict) -> list[dict]:
    user_id = player["user_id"] if player["user_id"] is not None else f"ai:{player['seat']}"
    tile = TILES[player["tile_id"]]
    actions = [
        {"id": f"MOVE:{destination}", "kind": "MOVE", "label": f"{TILES[destination]['label']} konumuna ilerle", "cost": "1 AP"}
        for destination in tile["adjacent"]
    ]
    if tile["type"] == "CAMP" and player["energy"] < 6:
        actions.append({"id": "REST", "kind": "REST", "label": "Dinlen (+2 enerji)", "cost": "1 AP"})
    if tile["type"] == "SALVAGE":
        flag = f"{state['round']}:{user_id}:{player['tile_id']}"
        if flag not in state["round_flags"]["scavenged"] and player["scrap"] < 6:
            actions.append({"id": "SCAVENGE", "kind": "SCAVENGE", "label": "Hurda topla (+1)", "cost": "1 AP"})
    if tile["type"] == "TRIAL" and tile.get("sigil") not in state["claimed_sigils"]:
        flag = f"{state['round']}:{user_id}:{player['tile_id']}"
        if flag not in state["round_flags"]["attempted_trials"]:
            for boost in range(min(2, player["energy"]) + 1):
                actions.append({"id": f"ATTEMPT_TRIAL:{boost}", "kind": "ATTEMPT_TRIAL", "label": f"Sınavı dene (+{boost} enerji)", "cost": "1 AP" + (f" + {boost} enerji" if boost else "")})
    if tile["type"] == "PORTAL":
        if player["sigils"]:
            actions.append({"id": "DEPOSIT_SIGIL", "kind": "DEPOSIT_SIGIL", "label": "Mührü portala yerleştir", "cost": "1 AP"})
        if state["portal_charge"] < 3 and player["scrap"] > 0:
            actions.append({"id": "CHARGE_PORTAL", "kind": "CHARGE_PORTAL", "label": "Portalı şarj et", "cost": "1 AP + 1 hurda"})
    actions.append({"id": "END_TURN", "kind": "END_TURN", "label": "Turu bitir", "cost": "0 AP"})
    return actions


def _roll_d6(seed: bytes, counter: int, purpose: str) -> tuple[int, int]:
    while True:
        digest = hmac.new(seed, f"{counter}:{purpose}".encode(), hashlib.sha256).digest()
        counter += 1
        for value in digest:
            if value < 252:
                return value % 6 + 1, counter


def _complete(state: dict, reason: str, seed: bytes) -> None:
    state["status"] = "COMPLETED"
    state["end_reason"] = reason
    state["group_outcome"] = "PORTAL_OPENED" if reason == "PORTAL_OPENED" else "ROUGH_ESCAPE"
    ranked = sorted(
        state["players"],
        key=lambda item: (item["fame"], item["contribution"], item["energy"] + item["scrap"], -item["seat"]),
        reverse=True,
    )
    state["winner_user_id"] = ranked[0]["user_id"]
    state["rng_seed_reveal"] = seed.hex()


def _advance_turn(state: dict, seed: bytes) -> None:
    seats = seat_count(state)
    points = action_points_for(seats)
    if state["turn_index"] < seats - 1:
        state["turn_index"] += 1
        first = (state["round"] - 1) % seats
        state["active_seat"] = (first + state["turn_index"]) % seats
        state["action_points"] = points
        return
    state["chaos"] = min(12, state["chaos"] + 1)
    if len(state["deposited_sigils"]) == 3 and state["portal_charge"] == 3:
        _complete(state, "PORTAL_OPENED", seed)
        return
    if state["chaos"] >= 12:
        _complete(state, "CHAOS_LIMIT", seed)
        return
    if state["round"] >= MAX_ROUNDS:
        _complete(state, "ROUND_LIMIT", seed)
        return
    state["round"] += 1
    state["turn_index"] = 0
    state["active_seat"] = (state["round"] - 1) % seats
    state["action_points"] = points
    state["round_flags"] = {"scavenged": [], "attempted_trials": []}
    lowest = min(item["fame"] for item in state["players"])
    trailing = [item for item in state["players"] if item["fame"] == lowest]
    for item in state["players"]:
        # Herkes başa başsa kimse momentum almaz; yalnız geride kalanlar alır.
        item["momentum"] = 1 if len(trailing) < seats and item in trailing else 0
        if item["energy"] == 0 and item["scrap"] == 0:
            item["energy"] = 1


def _actor_key(player: dict) -> str:
    """Tur bayraklarında kullanılan aktör anahtarı; AI koltuğu için ``ai:<koltuk>``."""
    return str(player["user_id"]) if player["user_id"] is not None else f"ai:{player['seat']}"


def apply_action(current: dict, user_id: int, action_id: str, seed: bytes, rng_counter: int) -> tuple[dict, dict, int]:
    legal = {item["id"]: item for item in legal_action_specs(current, user_id)}
    if action_id not in legal:
        raise ValueError("ILLEGAL_ACTION")
    return _apply(current, current["active_seat"], action_id, legal[action_id], seed, rng_counter)


def _apply(current: dict, seat: int, action_id: str, spec: dict, seed: bytes, rng_counter: int) -> tuple[dict, dict, int]:
    state = copy.deepcopy(current)
    player = player_by_seat(state, seat)
    user_id = _actor_key(player)
    tile = TILES[player["tile_id"]]
    summary = ""
    result: dict = {"kind": spec["kind"], "actor_user_id": player["user_id"], "actor_seat": seat, "actor_is_ai": player["ai"]}

    if action_id.startswith("MOVE:"):
        destination = action_id.split(":", 1)[1]
        player["tile_id"] = destination
        state["action_points"] -= 1
        summary = f"Oyuncu {TILES[destination]['label']} konumuna ilerledi."
        result["destination"] = destination
    elif action_id == "REST":
        gained = min(2, 6 - player["energy"])
        player["energy"] += gained
        state["action_points"] -= 1
        summary = f"Oyuncu kampta dinlenip {gained} enerji kazandı."
    elif action_id == "SCAVENGE":
        player["scrap"] += 1
        state["round_flags"]["scavenged"].append(f"{state['round']}:{user_id}:{player['tile_id']}")
        state["action_points"] -= 1
        summary = "Oyuncu güvenli hurdalıktan 1 hurda topladı."
    elif action_id.startswith("ATTEMPT_TRIAL:"):
        boost = int(action_id.rsplit(":", 1)[1])
        player["energy"] -= boost
        flag = f"{state['round']}:{user_id}:{player['tile_id']}"
        state["round_flags"]["attempted_trials"].append(flag)
        die, rng_counter = _roll_d6(seed, rng_counter, f"trial:{state['round']}:{user_id}:{player['tile_id']}")
        momentum = player["momentum"]
        player["momentum"] = 0
        total = die + boost + momentum
        success = total >= 5
        result.update({"die": die, "boost": boost, "momentum": momentum, "total": total, "success": success})
        if success:
            sigil = tile["sigil"]
            state["claimed_sigils"][sigil] = user_id
            player["sigils"].append(sigil)
            player["fame"] += 1
            summary = f"Oyuncu sınavı {total} toplamla geçti ve {sigil} mührünü aldı."
        else:
            if player["energy"] > 0:
                player["energy"] -= 1
            state["chaos"] = min(12, state["chaos"] + 1)
            summary = f"Oyuncu sınavda {total} toplamla başarısız oldu; Kaos 1 arttı."
        state["action_points"] -= 1
    elif action_id == "DEPOSIT_SIGIL":
        sigil = player["sigils"].pop(0)
        if sigil not in state["deposited_sigils"]:
            state["deposited_sigils"].append(sigil)
        player["fame"] += 2
        player["contribution"] += 1
        state["action_points"] -= 1
        summary = f"Oyuncu {sigil} mührünü Son Portal'a yerleştirdi."
    elif action_id == "CHARGE_PORTAL":
        player["scrap"] -= 1
        player["fame"] += 1
        player["contribution"] += 1
        state["portal_charge"] += 1
        state["action_points"] -= 1
        summary = f"Oyuncu portalı şarj etti; seviye {state['portal_charge']}/3 oldu."
    else:
        summary = "Oyuncu turunu tamamladı."

    if action_id == "END_TURN" or state["action_points"] == 0:
        _advance_turn(state, seed)
    result["mechanical_summary"] = summary
    result["round"] = state["round"]
    return state, result, rng_counter


def _next_step(origin: str, targets: set[str]) -> str | None:
    """``origin``'den ``targets``'a giden en kısa yolun ilk adımı (genişlik öncelikli)."""
    if not targets or origin in targets:
        return None
    queue = [(origin, None)]
    seen = {origin}
    while queue:
        tile_id, first = queue.pop(0)
        for neighbour in TILES[tile_id]["adjacent"]:
            if neighbour in seen:
                continue
            step = first or neighbour
            if neighbour in targets:
                return step
            seen.add(neighbour)
            queue.append((neighbour, step))
    return None


def ai_action_id(state: dict) -> str:
    """AI koltuğunun bir sonraki hamlesi — deterministik, modele sorulmaz.

    Öncelik sırası: elindeki mührü portala götür → üstünde durduğu sınavı dene →
    portalı şarj et → eksik hurdayı topla → enerjisi bittiyse kampta dinlen →
    en yakın hedefe ilerle. Hiçbiri mümkün değilse turu bitirir.
    """
    player = player_by_seat(state, state["active_seat"])
    legal = {item["id"] for item in _actions_for(state, player)}
    tile = TILES[player["tile_id"]]

    if "DEPOSIT_SIGIL" in legal:
        return "DEPOSIT_SIGIL"
    if tile["type"] == "TRIAL":
        boosts = sorted((int(item.rsplit(":", 1)[1]) for item in legal if item.startswith("ATTEMPT_TRIAL:")), reverse=True)
        if boosts:
            return f"ATTEMPT_TRIAL:{boosts[0]}"
    if "CHARGE_PORTAL" in legal and len(state["deposited_sigils"]) >= state["portal_charge"]:
        return "CHARGE_PORTAL"
    if "SCAVENGE" in legal and player["scrap"] < 2:
        return "SCAVENGE"
    if "REST" in legal and player["energy"] <= 1:
        return "REST"

    if player["sigils"]:
        targets = {"P"}
    else:
        unclaimed = {tile_id for tile_id, data in TILES.items() if data.get("sigil") and data["sigil"] not in state["claimed_sigils"]}
        if unclaimed:
            targets = unclaimed
        elif player["scrap"] > 0 and state["portal_charge"] < 3:
            targets = {"P"}
        else:
            targets = {tile_id for tile_id, data in TILES.items() if data["type"] == "SALVAGE"}
    step = _next_step(player["tile_id"], targets)
    if step and f"MOVE:{step}" in legal:
        return f"MOVE:{step}"
    return "END_TURN"


def apply_ai_action(current: dict, seed: bytes, rng_counter: int) -> tuple[dict, dict, int]:
    if not active_is_ai(current):
        raise ValueError("NOT_AI_TURN")
    player = player_by_seat(current, current["active_seat"])
    action_id = ai_action_id(current)
    spec = next(item for item in _actions_for(current, player) if item["id"] == action_id)
    return _apply(current, current["active_seat"], action_id, spec, seed, rng_counter)
