from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.modules.hidden_role_game.content import AI_PLAYER_NAME, MANDATES, OBJECTIVES, OFFICES, SCENARIOS, public_scenario
from app.modules.hidden_role_game.crypto import decrypt_json, encrypt_json
from app.modules.hidden_role_game.models import HiddenRoleAssignment, HiddenRoleClaim, HiddenRoleDeduction, HiddenRoleState, HiddenRoleVote
from app.modules.hidden_role_game.schemas import HiddenGameCreate
from app.platform.events import append_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceEvent, ExperienceSession, ExperienceSessionPlayer, utcnow
from app.platform.sessions import ai_seats, create_active_session, ensure_session_access, ensure_session_player, participant_key


def _seed(session_id: str) -> bytes:
    return hmac.new(settings.core_api_secret_key.encode(), f"hidden:{session_id}".encode(), hashlib.sha256).digest()


def _ordered(values: list[str], seed: bytes, purpose: str) -> list[str]:
    return sorted(values, key=lambda value: hmac.new(seed, f"{purpose}:{value}".encode(), hashlib.sha256).digest())


def _ai_value(seed: bytes, purpose: str) -> int:
    return int.from_bytes(hmac.new(seed, purpose.encode(), hashlib.sha256).digest()[:4], "big")


def _ai_claim(seed: bytes, scenario: dict, round_number: int, seat: int) -> dict:
    """AI koltuğunun iddiası — tohumdan türetilir, modele sorulmaz.

    Üçte bir olasılıkla yanlış yönlendiren bir iddia atar; aksi hâlde kendi ofis
    ipucuyla tutarlı konuşur. Böylece AI ne her turda haklı çıkar ne de rastgele olur.
    """
    value = _ai_value(seed, f"ai-claim:{round_number}:{seat}")
    safe = scenario["safe"]
    others = [option["id"] for option in scenario["options"] if option["id"] != safe]
    if value % 3 == 0:
        return {"subject_option_id": safe, "proposition": "EXCLUDES_SAFE", "flavor_text": "Bu seçenek bana fazla temiz görünüyor."}
    if value % 2:
        return {"subject_option_id": safe, "proposition": "SUPPORTS_SAFE", "flavor_text": "Kayıtlar bu yönü destekliyor."}
    return {"subject_option_id": others[value % len(others)], "proposition": "RISK_HIGH", "flavor_text": "Bu yolun riski hesaplanandan büyük."}


def _ai_vote(seed: bytes, scenario: dict, round_number: int, seat: int) -> str:
    """AI dört turun üçünde güvenli seçeneği oylar; biri tohumla sapar."""
    value = _ai_value(seed, f"ai-vote:{round_number}:{seat}")
    if value % 4:
        return scenario["safe"]
    others = [option["id"] for option in scenario["options"] if option["id"] != scenario["safe"]]
    return others[value % len(others)]


def _ai_deduction(seed: bytes, others: list[dict], seat: int) -> dict:
    """AI'ın diğer koltuklar için ofis/görev tahmini — deterministik ve kısmen isabetli."""
    offices = _ordered(OFFICES, seed, f"ai-guess-office:{seat}")
    mandates = _ordered(MANDATES, seed, f"ai-guess-mandate:{seat}")
    return {
        "office_by_key": {_pkey(item): offices[index % len(offices)] for index, item in enumerate(others)},
        "mandate_by_key": {_pkey(item): mandates[index % len(mandates)] for index, item in enumerate(others)},
    }


def _token(session_id: str, user_id: int, revision: int, phase: str) -> str:
    return hmac.new(settings.core_api_secret_key.encode(), f"hidden:{session_id}:{user_id}:{revision}:{phase}".encode(), hashlib.sha256).hexdigest()


def _session(db: Session, session_id: str, *, lock: bool = False) -> ExperienceSession:
    query = db.query(ExperienceSession).filter(ExperienceSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = query.first()
    if not session or session.module_type != "hidden_role_game":
        raise HTTPException(status_code=404, detail="Üç Mühür oturumu bulunamadı")
    return session


def _state(db: Session, session_id: str, *, lock: bool = False) -> HiddenRoleState:
    query = db.query(HiddenRoleState).filter(HiddenRoleState.session_id == session_id, HiddenRoleState.is_current.is_(True))
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=409, detail="Gizli rol durumu hazır değil")
    return row


def _pkey(player: dict) -> str:
    """Motor sözlüklerindeki katılımcı anahtarı; AI koltuğu ``ai:<koltuk>`` olur."""
    return participant_key(player["user_id"], player["seat"])


def _assignment(db: Session, session_id: str, user_id: int) -> dict:
    row = db.get(HiddenRoleAssignment, {"session_id": session_id, "user_id": user_id})
    if not row:
        raise HTTPException(status_code=409, detail="Gizli atama bulunamadı")
    return decrypt_json(row.encrypted_payload, aad=f"assignment:{session_id}:{user_id}")


def _assignment_of(db: Session, session_id: str, player: dict, engine: dict) -> dict:
    """AI koltuğunun gizli ataması tabloda değil, şifreli motor durumunda tutulur."""
    if player["ai"]:
        return engine["ai_assignments"][_pkey(player)]
    return _assignment(db, session_id, player["user_id"])


def _replace_state(db: Session, session: ExperienceSession, row: HiddenRoleState, public: dict, engine: dict) -> HiddenRoleState:
    row.is_current = False
    session.revision += 1
    next_row = HiddenRoleState(session_id=session.id, revision=session.revision, public_state=public, engine_ciphertext=encrypt_json(engine, aad=f"state:{session.id}:{session.revision}"), rng_commitment=row.rng_commitment)
    db.add(next_row)
    return next_row


def create_game(db: Session, *, server_id: int, actor: User, payload: HiddenGameCreate, idempotency_key: str) -> ExperienceSession:
    session = create_active_session(db, server_id=server_id, module_type="hidden_role_game", owner=actor, player_ids=payload.player_ids, idempotency_key=idempotency_key, settings={"rules_version": "three-seals-v1", "content_version": "three-seals-content-v1"}, ai_seat_count=payload.ai_players, min_seats=2, max_seats=3)
    if db.query(HiddenRoleState).filter(HiddenRoleState.session_id == session.id).first():
        return session
    seed = _seed(session.id)
    humans = sorted(session.players, key=lambda item: item.seat)
    participants = [{"user_id": player.user_id, "seat": player.seat, "ai": False} for player in humans]
    participants += [{"user_id": None, "seat": seat, "ai": True} for seat in ai_seats(session)]
    participants.sort(key=lambda item: item["seat"])
    offices = _ordered(OFFICES, seed, "office")
    mandates = _ordered(MANDATES, seed, "mandate")
    objectives = _ordered(OBJECTIVES, seed, "objective")
    ai_assignments: dict[str, dict] = {}
    for participant in participants:
        seat = participant["seat"]
        secret = {"office": offices[seat], "mandate": mandates[seat], "objective": objectives[seat % len(objectives)]}
        if participant["ai"]:
            ai_assignments[_pkey(participant)] = secret
            continue
        canonical = repr(sorted(secret.items())).encode()
        db.add(HiddenRoleAssignment(session_id=session.id, user_id=participant["user_id"], encrypted_payload=encrypt_json(secret, aad=f"assignment:{session.id}:{participant['user_id']}"), content_hash=hashlib.sha256(canonical).hexdigest()))
    keys = [_pkey(participant) for participant in participants]
    # AI iddiaları herkese açıktır ama hidden_role_claims tablosuna yazılamaz
    # (user_id sütunu users.id'ye FK'dir), bu yüzden public duruma konur.
    public = {"status": "ACTIVE", "round": 1, "phase": "CLAIM", "stability": 4, "players": [{**participant, "reputation": 3, "insight": 0} for participant in participants], "ai_claims": [], "round_results": [], "result": None}
    engine = {"secret_scores": {key: 0 for key in keys}, "safe_votes": {key: 0 for key in keys}, "supported_claims": {key: 0 for key in keys}, "vote_dispositions": {key: [] for key in keys}, "ai_assignments": ai_assignments}
    commitment = hashlib.sha256(seed).hexdigest()
    db.add(HiddenRoleState(session_id=session.id, revision=session.revision, public_state=public, engine_ciphertext=encrypt_json(engine, aad=f"state:{session.id}:{session.revision}"), rng_commitment=commitment))
    append_event(db, session, "hidden.game_started", {"player_ids": [player.user_id for player in humans], "ai_seats": ai_seats(session), "rng_commitment": commitment}, idempotency_key="hidden:start")
    db.commit()
    return _session(db, session.id)


def get_active_game(db: Session, *, server_id: int, actor: User) -> ExperienceSession | None:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    return db.query(ExperienceSession).join(ExperienceSessionPlayer, ExperienceSessionPlayer.session_id == ExperienceSession.id).filter(ExperienceSession.server_id == server_id, ExperienceSession.module_type == "hidden_role_game", ExperienceSession.status == "active", ExperienceSessionPlayer.user_id == actor.id).order_by(ExperienceSession.updated_at.desc()).first()


def _current_claims(db: Session, session_id: str, round_number: int, public: dict) -> list[dict]:
    human = [{"id": row.id, "user_id": row.user_id, "key": str(row.user_id), "subject_option_id": row.subject_option_id, "proposition": row.proposition, "flavor_text": row.flavor_text, "verdict": row.verdict} for row in db.query(HiddenRoleClaim).filter_by(session_id=session_id, round_number=round_number).order_by(HiddenRoleClaim.created_at).all()]
    ai = [{"id": None, "user_id": None, **{key: value for key, value in item.items() if key != "round"}} for item in public.get("ai_claims", []) if item["round"] == round_number]
    return [*human, *ai]


def game_view(db: Session, *, session_id: str, actor: User) -> dict:
    session = _session(db, session_id)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    row = _state(db, session.id)
    public = row.public_state
    assignment = _assignment(db, session.id, actor.id)
    crisis = public_scenario(public["round"] - 1) if public["phase"] != "COMPLETED" else None
    vote = db.query(HiddenRoleVote).filter_by(session_id=session.id, round_number=public["round"], user_id=actor.id).first()
    own_vote = decrypt_json(vote.encrypted_payload, aad=f"vote:{session.id}:{public['round']}:{actor.id}")["option_id"] if vote else None
    deduction = db.query(HiddenRoleDeduction).filter_by(session_id=session.id, user_id=actor.id).first()
    private = {**assignment, "clue": SCENARIOS[public["round"] - 1]["clues"][assignment["office"]] if crisis else None, "own_vote": own_vote, "deduction_submitted": deduction is not None}
    submitted_votes = db.query(HiddenRoleVote).filter_by(session_id=session.id, round_number=public["round"]).count() if public["phase"] != "COMPLETED" else 0
    submitted_deductions = db.query(HiddenRoleDeduction).filter_by(session_id=session.id).count()
    already_claimed = db.query(HiddenRoleClaim).filter_by(session_id=session.id, round_number=public["round"], user_id=actor.id).first() is not None if crisis else True
    legal = None
    if public["phase"] == "CLAIM" and not already_claimed:
        legal = {"kind": "CLAIM", "token": _token(session.id, actor.id, row.revision, "CLAIM")}
    elif public["phase"] == "VOTE" and not vote:
        legal = {"kind": "VOTE", "token": _token(session.id, actor.id, row.revision, "VOTE")}
    elif public["phase"] == "FINAL_DEDUCTION" and not deduction:
        legal = {"kind": "DEDUCTION", "token": _token(session.id, actor.id, row.revision, "FINAL_DEDUCTION")}
    names = {player.user_id: player.user.display_name or player.user.username for player in session.players}
    players = [{**item, "display_name": AI_PLAYER_NAME if item["ai"] else names[item["user_id"]], "key": _pkey(item)} for item in public["players"]]
    human_count = sum(1 for item in public["players"] if not item["ai"])
    recap_event = db.query(ExperienceEvent).filter_by(session_id=session.id, event_type="hidden.recap_ready").order_by(ExperienceEvent.id.desc()).first()
    return {"session_id": session.id, "server_id": session.server_id, "status": public["status"], "revision": row.revision, "round": public["round"], "phase": public["phase"], "stability": public["stability"], "crisis": crisis, "players": players, "human_player_count": human_count, "claims": _current_claims(db, session.id, public["round"], public) if crisis else [], "submitted_vote_count": submitted_votes, "submitted_deduction_count": submitted_deductions, "round_results": public["round_results"], "own_private": private, "legal_action": legal, "result": public["result"], "recap": recap_event.public_payload.get("text") if recap_event else None, "rng_commitment": row.rng_commitment}


def _check_command(session: ExperienceSession, row: HiddenRoleState, actor: User, phase: str, token: str, revision: int) -> None:
    if row.revision != revision:
        raise HTTPException(status_code=409, detail={"message": "Oyun revizyonu güncel değil", "current_revision": row.revision})
    if row.public_state["phase"] != phase:
        raise HTTPException(status_code=409, detail="Bu işlem mevcut fazda kullanılamaz")
    if not hmac.compare_digest(_token(session.id, actor.id, revision, phase), token):
        raise HTTPException(status_code=409, detail="Gizli işlem yetkisi geçersiz veya süresi dolmuş")


def submit_claim(db: Session, *, session_id: str, actor: User, subject: str, proposition: str, flavor: str, token: str, revision: int) -> dict:
    session = _session(db, session_id, lock=True); ensure_session_access(db, session, actor); ensure_session_player(db, session, actor.id)
    row = _state(db, session.id, lock=True); _check_command(session, row, actor, "CLAIM", token, revision)
    public = dict(row.public_state); round_number = public["round"]
    existing = db.query(HiddenRoleClaim).filter_by(session_id=session.id, round_number=round_number, user_id=actor.id).first()
    if existing:
        return game_view(db, session_id=session.id, actor=actor)
    claim = HiddenRoleClaim(session_id=session.id, round_number=round_number, user_id=actor.id, subject_option_id=subject, proposition=proposition, flavor_text=flavor)
    db.add(claim); db.flush()
    engine = decrypt_json(row.engine_ciphertext, aad=f"state:{session.id}:{row.revision}")
    humans = [item for item in public["players"] if not item["ai"]]
    if db.query(HiddenRoleClaim).filter_by(session_id=session.id, round_number=round_number).count() == len(humans):
        # İnsanlar konuştuktan sonra AI koltukları da iddiasını açar, sonra oylamaya geçilir.
        seed = _seed(session.id); scenario = SCENARIOS[round_number - 1]
        ai_claims = [{"round": round_number, "seat": item["seat"], "key": _pkey(item), "verdict": None, **_ai_claim(seed, scenario, round_number, item["seat"])} for item in public["players"] if item["ai"]]
        public["ai_claims"] = [*public["ai_claims"], *ai_claims]
        public["phase"] = "VOTE"
    _replace_state(db, session, row, public, engine)
    append_event(db, session, "hidden.claim_created", {"claim_id": claim.id, "user_id": actor.id, "subject_option_id": subject, "proposition": proposition, "flavor_text": flavor}, idempotency_key=f"hidden:claim:{round_number}:{actor.id}")
    db.commit(); return game_view(db, session_id=session.id, actor=actor)


def _claim_verdict(subject: str, proposition: str, safe: str) -> str:
    supported = (subject == safe and proposition in {"SUPPORTS_SAFE", "RISK_LOW"}) or (subject != safe and proposition in {"EXCLUDES_SAFE", "RISK_HIGH"})
    return "SUPPORTED" if supported else "CONTRADICTED"


def _score_claim(player: dict, verdict: str, engine: dict, key: str) -> None:
    """İddia sonucunu itibar ve içgörüye yansıtır — insan ve AI koltukları için ortak."""
    if verdict == "SUPPORTED":
        player["insight"] += 1
        player["reputation"] = min(5, player["reputation"] + 1)
        engine["supported_claims"][key] += 1
    else:
        player["reputation"] = max(1, player["reputation"] - 1)


def _group_outcome(stability: int) -> str:
    return "STABLE" if stability >= 3 else "FRACTURED" if stability >= 1 else "COLLAPSED"


def submit_vote(db: Session, *, session_id: str, actor: User, option_id: str, token: str, revision: int) -> dict:
    session = _session(db, session_id, lock=True); ensure_session_access(db, session, actor); ensure_session_player(db, session, actor.id)
    row = _state(db, session.id, lock=True); _check_command(session, row, actor, "VOTE", token, revision)
    public = {**row.public_state}; round_number = public["round"]
    existing = db.query(HiddenRoleVote).filter_by(session_id=session.id, round_number=round_number, user_id=actor.id).first()
    if existing:
        return game_view(db, session_id=session.id, actor=actor)
    raw = {"option_id": option_id}
    db.add(HiddenRoleVote(session_id=session.id, round_number=round_number, user_id=actor.id, encrypted_payload=encrypt_json(raw, aad=f"vote:{session.id}:{round_number}:{actor.id}"), content_hash=hashlib.sha256(option_id.encode()).hexdigest()))
    db.flush()
    engine = decrypt_json(row.engine_ciphertext, aad=f"state:{session.id}:{row.revision}")
    humans = [item for item in public["players"] if not item["ai"]]
    if db.query(HiddenRoleVote).filter_by(session_id=session.id, round_number=round_number).count() == len(humans):
        scenario = SCENARIOS[round_number - 1]; seed = _seed(session.id)
        by_key = {_pkey(item): item for item in public["players"]}
        votes = {}
        for vote in db.query(HiddenRoleVote).filter_by(session_id=session.id, round_number=round_number).all():
            votes[str(vote.user_id)] = decrypt_json(vote.encrypted_payload, aad=f"vote:{session.id}:{round_number}:{vote.user_id}")["option_id"]
        # AI oyu tabloya yazılmaz; tohumdan türetilir ve insanlar oyunu verdikten sonra açılır.
        for item in public["players"]:
            if item["ai"]:
                votes[_pkey(item)] = _ai_vote(seed, scenario, round_number, item["seat"])
        counts = {choice: list(votes.values()).count(choice) for choice in ["A", "B", "C"]}
        top = max(counts.values())
        # Çoğunluk koltukların yarısından fazlasıdır: üç koltukta eski "en az iki oy"
        # kuralıyla aynı, iki koltukta ikisinin de aynı seçimi yapmasını ister.
        selected = next((choice for choice, count in counts.items() if count == top and count * 2 > len(votes)), None)
        if selected is None:
            # Beraberlikte hakem koltuğu karar verir; koltuk sayısına göre döner.
            arbiter_seat = (round_number - 1) % len(public["players"])
            arbiter_key = next(key for key, item in by_key.items() if item["seat"] == arbiter_seat)
            selected = votes[arbiter_key]
        verdicts = []
        for claim in db.query(HiddenRoleClaim).filter_by(session_id=session.id, round_number=round_number).all():
            claim.verdict = _claim_verdict(claim.subject_option_id, claim.proposition, scenario["safe"])
            _score_claim(by_key[str(claim.user_id)], claim.verdict, engine, str(claim.user_id))
            verdicts.append({"claim_id": claim.id, "key": str(claim.user_id), "verdict": claim.verdict})
        for ai_claim in public["ai_claims"]:
            if ai_claim["round"] != round_number:
                continue
            ai_claim["verdict"] = _claim_verdict(ai_claim["subject_option_id"], ai_claim["proposition"], scenario["safe"])
            _score_claim(by_key[ai_claim["key"]], ai_claim["verdict"], engine, ai_claim["key"])
            verdicts.append({"claim_id": None, "key": ai_claim["key"], "verdict": ai_claim["verdict"]})
        disposition_by_id = {option["id"]: option["disposition"] for option in scenario["options"]}
        for key, choice in votes.items():
            player = by_key[key]
            engine["vote_dispositions"][key].append(disposition_by_id[choice])
            if choice == scenario["safe"]:
                player["insight"] += 1; engine["safe_votes"][key] += 1
            assignment = _assignment_of(db, session.id, player, engine)
            if disposition_by_id[selected] == assignment["mandate"]:
                engine["secret_scores"][key] = min(2, engine["secret_scores"][key] + 1)
        if selected != scenario["safe"]:
            public["stability"] = max(0, public["stability"] - scenario["severity"])
        public["round_results"] = [*public["round_results"], {"round": round_number, "selected_option_id": selected, "safe_option_id": scenario["safe"], "votes": votes, "claim_verdicts": verdicts, "stability": public["stability"]}]
        if round_number >= 4 or public["stability"] == 0:
            public["phase"] = "FINAL_DEDUCTION"
        else:
            public["round"] += 1; public["phase"] = "CLAIM"
    _replace_state(db, session, row, public, engine)
    append_event(db, session, "hidden.vote_received", {"user_id": actor.id, "round": round_number}, idempotency_key=f"hidden:vote:{round_number}:{actor.id}")
    if public["phase"] in {"CLAIM", "FINAL_DEDUCTION"}:
        append_event(db, session, "hidden.round_resolved", public["round_results"][-1], idempotency_key=f"hidden:resolve:{round_number}")
    db.commit(); return game_view(db, session_id=session.id, actor=actor)


def _objective_score(objective: str, player: dict, key: str, engine: dict) -> int:
    if objective == "SAFE_THREE": return 2 if engine["safe_votes"][key] >= 3 else 0
    if objective == "SUPPORTED_THREE": return 2 if engine["supported_claims"][key] >= 3 else 0
    if objective == "VARIED_VOTES": return 2 if len(set(engine["vote_dispositions"][key])) >= 3 else 0
    return 2 if player["reputation"] >= 3 else 0


def submit_deduction(db: Session, *, session_id: str, actor: User, offices: dict[str, str], mandates: dict[str, str], token: str, revision: int) -> dict:
    session = _session(db, session_id, lock=True); ensure_session_access(db, session, actor); ensure_session_player(db, session, actor.id)
    row = _state(db, session.id, lock=True); _check_command(session, row, actor, "FINAL_DEDUCTION", token, revision)
    public = {**row.public_state}; existing = db.query(HiddenRoleDeduction).filter_by(session_id=session.id, user_id=actor.id).first()
    if existing: return game_view(db, session_id=session.id, actor=actor)
    by_key = {_pkey(item): item for item in public["players"]}
    expected = set(by_key) - {str(actor.id)}
    if set(offices) != expected or set(mandates) != expected:
        raise HTTPException(status_code=422, detail=f"Diğer {len(expected)} koltuk için eksiksiz tahmin gerekli")
    payload = {"office_by_key": dict(offices), "mandate_by_key": dict(mandates)}
    canonical = repr(payload).encode()
    db.add(HiddenRoleDeduction(session_id=session.id, user_id=actor.id, encrypted_payload=encrypt_json(payload, aad=f"deduction:{session.id}:{actor.id}"), content_hash=hashlib.sha256(canonical).hexdigest())); db.flush()
    engine = decrypt_json(row.engine_ciphertext, aad=f"state:{session.id}:{row.revision}")
    humans = [item for item in public["players"] if not item["ai"]]
    if db.query(HiddenRoleDeduction).filter_by(session_id=session.id).count() == len(humans):
        seed = _seed(session.id)
        assignments = {_pkey(item): _assignment_of(db, session.id, item, engine) for item in public["players"]}
        scores = []
        for player in public["players"]:
            key = _pkey(player)
            others = [item for item in public["players"] if _pkey(item) != key]
            if player["ai"]:
                # AI'ın tahmini de tabloya yazılmaz; aynı tohumdan üretilir.
                guesses = _ai_deduction(seed, others, player["seat"])
            else:
                deduction = db.query(HiddenRoleDeduction).filter_by(session_id=session.id, user_id=player["user_id"]).one()
                guesses = decrypt_json(deduction.encrypted_payload, aad=f"deduction:{session.id}:{player['user_id']}")
            office_points = 1 if all(guesses["office_by_key"].get(_pkey(other)) == assignments[_pkey(other)]["office"] for other in others) else 0
            mandate_points = 1 if all(guesses["mandate_by_key"].get(_pkey(other)) == assignments[_pkey(other)]["mandate"] for other in others) else 0
            objective_points = _objective_score(assignments[key]["objective"], player, key, engine)
            total = player["insight"] + engine["secret_scores"][key] + office_points + mandate_points + objective_points
            scores.append({"key": key, "user_id": player["user_id"], "ai": player["ai"], "insight": player["insight"], "mandate_points": engine["secret_scores"][key], "objective_points": objective_points, "deduction_points": office_points + mandate_points, "total": total, "reputation": player["reputation"]})
        ranked = sorted(scores, key=lambda score: (score["total"], score["reputation"], engine["safe_votes"][score["key"]], engine["supported_claims"][score["key"]]), reverse=True)
        public["status"] = "COMPLETED"; public["phase"] = "COMPLETED"
        public["result"] = {"group_outcome": _group_outcome(public["stability"]), "winner_key": ranked[0]["key"], "winner_user_id": ranked[0]["user_id"], "scores": scores, "assignments": assignments}
        session.status = "ended"; session.ended_at = utcnow()
    next_row = _replace_state(db, session, row, public, engine)
    append_event(db, session, "hidden.deduction_received", {"user_id": actor.id}, idempotency_key=f"hidden:deduction:{actor.id}")
    if public["phase"] == "COMPLETED":
        event = append_event(db, session, "hidden.roles_revealed", public["result"], idempotency_key="hidden:revealed")
        enqueue_job(db, module="hidden_role_game", job_type="hidden.end_recap", idempotency_key=f"hidden:recap:{event.id}", input_ref={"event_id": event.id}, session_id=session.id, actor_id=actor.id, priority=1)
    db.commit(); return game_view(db, session_id=session.id, actor=actor)
