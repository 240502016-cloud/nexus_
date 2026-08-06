from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.modules.ai_board_game.engine import AI_PLAYER_NAME, TILES, active_is_ai, active_user_id, apply_ai_action, apply_action, initial_state, legal_action_specs
from app.modules.ai_board_game.models import BoardGameAction, BoardGameState
from app.modules.ai_board_game.schemas import BoardGameCreate
from app.platform.events import append_event, serialize_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceEvent, ExperienceSession, ExperienceSessionPlayer, utcnow
from app.platform.sessions import ai_seats, create_active_session, ensure_session_access, ensure_session_player


def _seed(session_id: str) -> bytes:
    return hmac.new(settings.core_api_secret_key.encode(), f"board:{session_id}".encode(), hashlib.sha256).digest()


def _action_token(session_id: str, user_id: int, revision: int, action_id: str) -> str:
    message = f"{session_id}:{user_id}:{revision}:{action_id}".encode()
    return hmac.new(settings.core_api_secret_key.encode(), message, hashlib.sha256).hexdigest()


def _session(db: Session, session_id: str, *, lock: bool = False) -> ExperienceSession:
    query = db.query(ExperienceSession).filter(ExperienceSession.id == session_id)
    if lock:
        query = query.with_for_update()
    session = query.first()
    if not session or session.module_type != "ai_board_game":
        raise HTTPException(status_code=404, detail="Son Portal oturumu bulunamadı")
    return session


def _current_state(db: Session, session_id: str, *, lock: bool = False) -> BoardGameState:
    query = db.query(BoardGameState).filter(BoardGameState.session_id == session_id, BoardGameState.is_current.is_(True))
    if lock:
        query = query.with_for_update()
    row = query.first()
    if not row:
        raise HTTPException(status_code=409, detail="Oyun durumu başlatılmamış")
    return row


def create_game(db: Session, *, server_id: int, actor: User, payload: BoardGameCreate, idempotency_key: str) -> ExperienceSession:
    session = create_active_session(
        db,
        server_id=server_id,
        module_type="ai_board_game",
        owner=actor,
        player_ids=payload.player_ids,
        idempotency_key=idempotency_key,
        settings={"theme": payload.theme, "rules_version": "last-portal-v1"},
        ai_seat_count=payload.ai_players,
        min_seats=2,
        max_seats=3,
    )
    if db.query(BoardGameState).filter(BoardGameState.session_id == session.id).first():
        return session
    ordered_ids = [row.user_id for row in sorted(session.players, key=lambda item: item.seat)]
    state = initial_state(ordered_ids, ai_seats=ai_seats(session))
    seed = _seed(session.id)
    db.add(BoardGameState(session_id=session.id, revision=session.revision, public_state=state, engine_state={"content_version": "last-portal-content-v1"}, rng_commitment=hashlib.sha256(seed).hexdigest(), rng_counter=0))
    append_event(db, session, "board.game_started", {"rules_version": "last-portal-v1", "player_ids": ordered_ids, "ai_seats": ai_seats(session), "rng_commitment": hashlib.sha256(seed).hexdigest()}, idempotency_key="board:start")
    db.commit()
    return _session(db, session.id)


def get_active_game(db: Session, *, server_id: int, actor: User) -> ExperienceSession | None:
    server = db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    return (
        db.query(ExperienceSession)
        .join(ExperienceSessionPlayer, ExperienceSessionPlayer.session_id == ExperienceSession.id)
        .filter(ExperienceSession.server_id == server_id, ExperienceSession.module_type == "ai_board_game", ExperienceSession.status == "active", ExperienceSessionPlayer.user_id == actor.id)
        .order_by(ExperienceSession.updated_at.desc())
        .first()
    )


def game_view(db: Session, *, session_id: str, actor: User) -> dict:
    session = _session(db, session_id)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    row = _current_state(db, session.id)
    state = row.public_state
    actions = []
    for spec in legal_action_specs(state, actor.id):
        actions.append({**spec, "token": _action_token(session.id, actor.id, row.revision, spec["id"])})
    names = {player.user_id: (player.user.display_name or player.user.username) for player in session.players}
    players = [{**item, "display_name": AI_PLAYER_NAME if item["ai"] else names.get(item["user_id"], f"Oyuncu #{item['user_id']}")} for item in state["players"]]
    event_rows = db.query(ExperienceEvent).filter(ExperienceEvent.session_id == session.id, ExperienceEvent.audience == "PUBLIC").order_by(ExperienceEvent.sequence.desc()).limit(30).all()
    events = [serialize_event(event) for event in reversed(event_rows)]
    return {
        "session_id": session.id,
        "server_id": session.server_id,
        "status": state["status"],
        "revision": row.revision,
        "rules_version": state["rules_version"],
        "theme": (session.settings or {}).get("theme", "ARCANE_RUINS"),
        "round": state["round"],
        "maximum_rounds": state["maximum_rounds"],
        "active_user_id": active_user_id(state) if state["status"] == "ACTIVE" else None,
        "active_seat": state["active_seat"] if state["status"] == "ACTIVE" else None,
        "active_is_ai": active_is_ai(state),
        "seat_count": len(state["players"]),
        "action_points": state["action_points"],
        "chaos": state["chaos"],
        "chaos_limit": state["chaos_limit"],
        "portal_charge": state["portal_charge"],
        "deposited_sigils": state["deposited_sigils"],
        "players": players,
        "tiles": TILES,
        "legal_actions": actions,
        "events": events,
        "group_outcome": state["group_outcome"],
        "winner_user_id": state["winner_user_id"],
        "end_reason": state["end_reason"],
        "rng_commitment": row.rng_commitment,
        "rng_seed_reveal": state["rng_seed_reveal"],
    }


def submit_action(db: Session, *, session_id: str, actor: User, action_id: str, action_token: str, expected_revision: int, idempotency_key: str) -> dict:
    session = _session(db, session_id, lock=True)
    ensure_session_access(db, session, actor)
    ensure_session_player(db, session, actor.id)
    prior = db.query(BoardGameAction).filter_by(session_id=session.id, actor_id=actor.id, idempotency_key=idempotency_key).first()
    if prior:
        return game_view(db, session_id=session.id, actor=actor)
    state_row = _current_state(db, session.id, lock=True)
    if state_row.revision != expected_revision:
        raise HTTPException(status_code=409, detail={"message": "Oyun revizyonu güncel değil", "current_revision": state_row.revision})
    expected_token = _action_token(session.id, actor.id, expected_revision, action_id)
    if not hmac.compare_digest(expected_token, action_token):
        raise HTTPException(status_code=409, detail="Aksiyon yetkisi geçersiz veya süresi dolmuş")
    seed = _seed(session.id)
    try:
        next_state, result, next_counter = apply_action(state_row.public_state, actor.id, action_id, seed, state_row.rng_counter)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Bu aksiyon mevcut durumda yasal değil") from exc
    # Sıra AI koltuğuna geçtiyse AI kendi turunu burada bitirir; insan oyuncu
    # kilitli kalmaz. Her hamle ayrı bir olay olarak kaydedilir.
    ai_results = []
    while next_state["status"] == "ACTIVE" and active_is_ai(next_state):
        next_state, ai_result, next_counter = apply_ai_action(next_state, seed, next_counter)
        ai_results.append(ai_result)
    state_row.is_current = False
    session.revision += 1
    if next_state["status"] == "COMPLETED":
        session.status = "ended"
        session.ended_at = utcnow()
    db.add(BoardGameState(session_id=session.id, revision=session.revision, public_state=next_state, engine_state=state_row.engine_state, rng_commitment=state_row.rng_commitment, rng_counter=next_counter))
    action = BoardGameAction(session_id=session.id, actor_id=actor.id, idempotency_key=idempotency_key, action_id=action_id, expected_revision=expected_revision, applied_revision=session.revision, result=result)
    db.add(action)
    event = append_event(db, session, "board.action_resolved", {**result, "action_id": action_id, "revision": session.revision}, idempotency_key=f"board:action:{action.id}")
    enqueue_job(db, module="ai_board_game", job_type="board.narrate", idempotency_key=f"board:narrate:{event.id}", input_ref={"event_id": event.id}, session_id=session.id, actor_id=actor.id, priority=1)
    for index, ai_result in enumerate(ai_results):
        # AI hamleleri board_game_actions tablosuna yazılmaz (actor_id users.id'ye FK'dir),
        # yalnız olay akışında görünür.
        ai_event = append_event(db, session, "board.action_resolved", {**ai_result, "revision": session.revision}, idempotency_key=f"board:ai:{session.revision}:{index}")
        enqueue_job(db, module="ai_board_game", job_type="board.narrate", idempotency_key=f"board:narrate:{ai_event.id}", input_ref={"event_id": ai_event.id}, session_id=session.id, actor_id=actor.id, priority=1)
    if next_state["status"] == "COMPLETED":
        append_event(db, session, "board.game_completed", {"group_outcome": next_state["group_outcome"], "winner_user_id": next_state["winner_user_id"], "end_reason": next_state["end_reason"]}, idempotency_key="board:completed")
    db.commit()
    return game_view(db, session_id=session.id, actor=actor)
