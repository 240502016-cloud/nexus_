from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.modules.shared_story.engine import ARCHETYPES, JOINT_CHOICES, TRAITS, active_is_ai, active_seat, active_user_id, ai_joint_choice, apply_ai_spotlight, apply_spotlight, initial_state, legal_spotlight_choices, resolve_joint
from app.modules.shared_story.models import StoryAction, StoryCharacter, StoryChoiceVote, StorySafetyProfile, StoryState
from app.modules.shared_story.schemas import StoryCreate, StorySafetyUpdate
from app.platform.crypto import decrypt_json, encrypt_json
from app.platform.events import append_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceEvent, ExperienceSession, ExperienceSessionPlayer, utcnow
from app.platform.sessions import ai_seats, create_active_session, ensure_session_access, ensure_session_player


def _seed(session_id: str) -> bytes: return hmac.new(settings.core_api_secret_key.encode(), f"story:{session_id}".encode(), hashlib.sha256).digest()
def _token(session_id: str, user_id: int, revision: int, phase: str) -> str: return hmac.new(settings.core_api_secret_key.encode(), f"story:{session_id}:{user_id}:{revision}:{phase}".encode(), hashlib.sha256).hexdigest()


def _session(db: Session, session_id: str, *, lock: bool = False) -> ExperienceSession:
    query = db.query(ExperienceSession).filter(ExperienceSession.id == session_id)
    if lock: query = query.with_for_update()
    session = query.first()
    if not session or session.module_type != "shared_story": raise HTTPException(status_code=404, detail="Ortak Hikâye oturumu bulunamadı")
    return session


def _state(db: Session, session_id: str, *, lock: bool = False) -> StoryState:
    query = db.query(StoryState).filter(StoryState.session_id == session_id, StoryState.is_current.is_(True))
    if lock: query = query.with_for_update()
    row = query.first()
    if not row: raise HTTPException(status_code=409, detail="Hikâye durumu hazır değil")
    return row


def get_safety_profile(db: Session, *, server_id: int, actor: User) -> StorySafetyProfile | dict:
    server = db.get(Server, server_id)
    if not server: raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    row = db.get(StorySafetyProfile, {"server_id": server_id, "user_id": actor.id})
    return row or {"server_id": server_id, "user_id": actor.id, "horror_level": 1, "violence_level": 1, "romance": "OFF", "player_conflict": "COOPERATIVE", "betrayal": "OFF", "personal_jokes": False, "dark_humor": False, "version": 1, "updated_at": utcnow()}


def update_safety_profile(db: Session, *, server_id: int, actor: User, payload: StorySafetyUpdate) -> StorySafetyProfile:
    get_safety_profile(db, server_id=server_id, actor=actor)
    row = db.get(StorySafetyProfile, {"server_id": server_id, "user_id": actor.id}); values = payload.model_dump()
    if not row: row = StorySafetyProfile(server_id=server_id, user_id=actor.id, **values); db.add(row)
    else:
        if any(getattr(row, key) != value for key, value in values.items()): row.version += 1
        for key, value in values.items(): setattr(row, key, value)
    db.commit(); return db.get(StorySafetyProfile, {"server_id": server_id, "user_id": actor.id})


def _profile_values(row: StorySafetyProfile | None) -> dict:
    return {"horror_level": row.horror_level if row else 1, "violence_level": row.violence_level if row else 1, "romance": row.romance if row else "OFF", "player_conflict": row.player_conflict if row else "COOPERATIVE", "betrayal": row.betrayal if row else "OFF", "personal_jokes": row.personal_jokes if row else False, "dark_humor": row.dark_humor if row else False}


def _envelope(db: Session, server_id: int, player_ids: list[int]) -> dict:
    profiles = [_profile_values(db.get(StorySafetyProfile, {"server_id": server_id, "user_id": user_id})) for user_id in player_ids]
    return {"horror_level": min(item["horror_level"] for item in profiles), "violence_level": min(item["violence_level"] for item in profiles), "romance": "OFF" if any(item["romance"] == "OFF" for item in profiles) else "SOFT", "player_conflict": "COOPERATIVE" if any(item["player_conflict"] == "COOPERATIVE" for item in profiles) else "CONTROLLED", "betrayal": "OFF" if any(item["betrayal"] == "OFF" for item in profiles) else "NPC_ONLY", "personal_jokes": all(item["personal_jokes"] for item in profiles), "dark_humor": all(item["dark_humor"] for item in profiles)}


def create_story(db: Session, *, server_id: int, actor: User, payload: StoryCreate, idempotency_key: str) -> ExperienceSession:
    chapter_count = {"SHORT": 2, "STANDARD": 3, "LONG": 4}[payload.length]
    session = create_active_session(db, server_id=server_id, module_type="shared_story", owner=actor, player_ids=payload.player_ids, idempotency_key=idempotency_key, settings={"theme": payload.theme, "length": payload.length, "use_party_lore": payload.use_party_lore, "rules_version": "three-paths-v1"}, ai_seat_count=payload.ai_players, min_seats=2, max_seats=3)
    if db.query(StoryState).filter_by(session_id=session.id).first(): return session
    players = sorted(session.players, key=lambda item: item.seat); ids = [item.user_id for item in players]
    for player in players:
        name = player.user.display_name or player.user.username
        db.add(StoryCharacter(session_id=session.id, user_id=player.user_id, seat=player.seat, name=name, archetype=ARCHETYPES[player.seat], traits=TRAITS[player.seat]))
    # AI koltuğu için tablo satırı yok; adı ve arketipi public_state içinde yaşar.
    public = initial_state(ids, ai_seats=ai_seats(session), theme=payload.theme, chapter_count=chapter_count, safety=_envelope(db, server_id, ids)); seed = _seed(session.id)
    db.add(StoryState(session_id=session.id, revision=session.revision, public_state=public, private_state_ciphertext=encrypt_json({"private_notes": {}}, aad=f"story-state:{session.id}:{session.revision}"), rng_counter=0, rng_commitment=hashlib.sha256(seed).hexdigest(), reason="OPENING"))
    event = append_event(db, session, "story.opening_committed", {"title": public["title"], "primary_goal": public["primary_goal"], "theme": payload.theme, "safety_envelope": public["safety_envelope"]}, idempotency_key="story:opening")
    enqueue_job(db, module="shared_story", job_type="story.scene_write", idempotency_key=f"story:prose:{event.id}", input_ref={"event_id": event.id, "content_kind": "OPENING"}, session_id=session.id, actor_id=actor.id, priority=2)
    db.commit(); return _session(db, session.id)


def get_active_story(db: Session, *, server_id: int, actor: User) -> ExperienceSession | None:
    server = db.get(Server, server_id)
    if not server: raise HTTPException(status_code=404, detail="Sunucu bulunamadı")
    ensure_server_member(db, server, actor)
    return db.query(ExperienceSession).join(ExperienceSessionPlayer, ExperienceSessionPlayer.session_id == ExperienceSession.id).filter(ExperienceSession.server_id == server_id, ExperienceSession.module_type == "shared_story", ExperienceSession.status == "active", ExperienceSessionPlayer.user_id == actor.id).order_by(ExperienceSession.updated_at.desc()).first()


def story_view(db: Session, *, session_id: str, actor: User) -> dict:
    session = _session(db, session_id); ensure_session_access(db, session, actor); ensure_session_player(db, session, actor.id); row = _state(db, session.id); state = row.public_state
    characters = {item.user_id: item for item in db.query(StoryCharacter).filter_by(session_id=session.id).all()}
    # AI karakterinin tablo satırı yok; adı/arketipi doğrudan durumdan gelir.
    projected = [item if item["ai"] else {**item, "name": characters[item["user_id"]].name, "archetype": characters[item["user_id"]].archetype, "traits": characters[item["user_id"]].traits} for item in state["characters"]]
    vote = db.query(StoryChoiceVote).filter_by(session_id=session.id, chapter_number=state["chapter"], user_id=actor.id).first()
    own_vote = decrypt_json(vote.encrypted_choice, aad=f"story-vote:{session.id}:{state['chapter']}:{actor.id}")["choice_id"] if vote else None
    active = active_user_id(state); token = None
    if state["phase"] == "SPOTLIGHT" and active == actor.id: token = _token(session.id, actor.id, row.revision, "SPOTLIGHT")
    elif state["phase"] == "JOINT_VOTE" and not vote: token = _token(session.id, actor.id, row.revision, "JOINT_VOTE")
    event_rows = db.query(ExperienceEvent).filter(ExperienceEvent.session_id == session.id, ExperienceEvent.event_type == "story.prose_ready").order_by(ExperienceEvent.sequence).all()
    prose = [event.public_payload for event in event_rows]
    return {"session_id": session.id, "server_id": session.server_id, "status": state["status"], "revision": row.revision, "title": state["title"], "primary_goal": state["primary_goal"], "theme": state["theme"], "chapter": state["chapter"], "chapter_count": state["chapter_count"], "phase": state["phase"], "active_user_id": active, "active_seat": active_seat(state), "active_is_ai": active_is_ai(state), "seat_count": len(state["characters"]), "scene_number": state["scene_number"], "threat": state["threat"], "goal_progress": state["goal_progress"], "mystery_progress": state["mystery_progress"], "bond": state["bond"], "characters": projected, "safety_envelope": state["safety_envelope"], "spotlight_choices": legal_spotlight_choices(state, actor.id), "joint_choices": JOINT_CHOICES if state["phase"] == "JOINT_VOTE" else [], "submitted_vote_count": db.query(StoryChoiceVote).filter_by(session_id=session.id, chapter_number=state["chapter"]).count() if state["phase"] == "JOINT_VOTE" else 0, "own_vote": own_vote, "action_token": token, "chapter_results": state["chapter_results"], "ending_vector": state["ending_vector"], "prose": prose, "rng_commitment": row.rng_commitment}


def _check(row: StoryState, session: ExperienceSession, actor: User, phase: str, token: str, revision: int) -> None:
    if row.revision != revision: raise HTTPException(status_code=409, detail={"message": "Hikâye revizyonu güncel değil", "current_revision": row.revision})
    if row.public_state["phase"] != phase or not hmac.compare_digest(_token(session.id, actor.id, revision, phase), token): raise HTTPException(status_code=409, detail="Hikâye eylem yetkisi geçersiz veya süresi dolmuş")


def _replace(db: Session, session: ExperienceSession, row: StoryState, state: dict, counter: int, reason: str) -> StoryState:
    private = decrypt_json(row.private_state_ciphertext, aad=f"story-state:{session.id}:{row.revision}"); row.is_current = False; session.revision += 1
    next_row = StoryState(session_id=session.id, revision=session.revision, public_state=state, private_state_ciphertext=encrypt_json(private, aad=f"story-state:{session.id}:{session.revision}"), rng_counter=counter, rng_commitment=row.rng_commitment, reason=reason); db.add(next_row); return next_row


def _play_ai_spotlights(state: dict, seed: bytes, counter: int) -> tuple[dict, list[dict], int]:
    """Sıra AI koltuğundayken sahneleri arka arkaya oynatır.

    Bir bölümün ilk sahnesi AI'a düşebileceği için (sıra her bölümde kayar) bu,
    hem insan hamlesinden hem de bölüm geçişinden sonra çağrılmalıdır.
    """
    scenes: list[dict] = []
    while state["status"] == "ACTIVE" and state["phase"] == "SPOTLIGHT" and active_is_ai(state):
        state, result, counter = apply_ai_spotlight(state, seed, counter)
        scenes.append(result)
    return state, scenes, counter


def _commit_scenes(db: Session, session: ExperienceSession, scenes: list[dict], actor: User, *, first_key: str | None = None) -> None:
    """Her sahne için olay yazar ve düzyazı işini kuyruğa bırakır."""
    for index, scene in enumerate(scenes):
        key = first_key if index == 0 and first_key else f"story:ai-action:{scene['chapter']}:{scene['scene_number']}"
        event = append_event(db, session, "story.action_committed", scene, idempotency_key=key)
        enqueue_job(db, module="shared_story", job_type="story.scene_write", idempotency_key=f"story:prose:{event.id}", input_ref={"event_id": event.id, "content_kind": "SCENE"}, session_id=session.id, actor_id=actor.id, priority=2)


def submit_action(db: Session, *, session_id: str, actor: User, action_id: str, token: str, revision: int, idempotency_key: str) -> dict:
    session = _session(db, session_id, lock=True); ensure_session_access(db, session, actor); ensure_session_player(db, session, actor.id)
    prior = db.query(StoryAction).filter_by(session_id=session.id, user_id=actor.id, idempotency_key=idempotency_key).first()
    if prior: return story_view(db, session_id=session.id, actor=actor)
    row = _state(db, session.id, lock=True); _check(row, session, actor, "SPOTLIGHT", token, revision)
    seed = _seed(session.id)
    try: state, result, counter = apply_spotlight(row.public_state, actor.id, action_id, seed, row.rng_counter)
    except ValueError as exc: raise HTTPException(status_code=409, detail="Bu sahne eylemi yasal değil") from exc
    state, ai_scenes, counter = _play_ai_spotlights(state, seed, counter)
    scenes = [result, *ai_scenes]
    _replace(db, session, row, state, counter, "ACTION")
    action = StoryAction(session_id=session.id, user_id=actor.id, chapter_number=result["chapter"], scene_number=result["scene_number"], idempotency_key=idempotency_key, action_id=action_id, outcome=result["outcome"], effect_payload=result["effects"], applied_revision=session.revision); db.add(action); db.flush()
    _commit_scenes(db, session, scenes, actor, first_key=f"story:action:{action.id}")
    db.commit(); return story_view(db, session_id=session.id, actor=actor)


def submit_vote(db: Session, *, session_id: str, actor: User, choice_id: str, token: str, revision: int) -> dict:
    session = _session(db, session_id, lock=True); ensure_session_access(db, session, actor); ensure_session_player(db, session, actor.id); row = _state(db, session.id, lock=True); _check(row, session, actor, "JOINT_VOTE", token, revision)
    chapter = row.public_state["chapter"]; existing = db.query(StoryChoiceVote).filter_by(session_id=session.id, chapter_number=chapter, user_id=actor.id).first()
    if existing: return story_view(db, session_id=session.id, actor=actor)
    salt = hashlib.sha256(f"{session.id}:{chapter}:{actor.id}:{choice_id}:{revision}".encode()).hexdigest(); db.add(StoryChoiceVote(session_id=session.id, chapter_number=chapter, user_id=actor.id, encrypted_choice=encrypt_json({"choice_id": choice_id, "salt": salt}, aad=f"story-vote:{session.id}:{chapter}:{actor.id}"), choice_commitment=hashlib.sha256((salt + choice_id).encode()).hexdigest())); db.flush()
    state = row.public_state; counter = row.rng_counter; resolved = None; votes_public = None; seed = _seed(session.id); ai_scenes: list[dict] = []
    votes = db.query(StoryChoiceVote).filter_by(session_id=session.id, chapter_number=chapter).all()
    human_seats = [item["seat"] for item in state["characters"] if not item["ai"]]
    if len(votes) == len(human_seats):
        choices = {vote.user_id: decrypt_json(vote.encrypted_choice, aad=f"story-vote:{session.id}:{chapter}:{vote.user_id}")["choice_id"] for vote in votes}
        # AI koltuğunun oyu tabloya yazılmaz; tohumdan deterministik türetilir.
        ballot = dict(choices)
        for item in state["characters"]:
            if item["ai"]:
                ai_choice, counter = ai_joint_choice(state, seed, counter); ballot[f"ai:{item['seat']}"] = ai_choice
        counts = {choice["id"]: list(ballot.values()).count(choice["id"]) for choice in JOINT_CHOICES}; top = max(counts.values())
        # Çoğunluk: koltukların yarısından fazlası. Üç koltukta bu eski "en az iki oy"
        # kuralıyla aynıdır; iki koltukta iki oyuncunun da aynı seçimi yapmasını ister.
        selected = next((key for key, count in counts.items() if count == top and count * 2 > len(ballot)), None)
        if not selected:
            leader_seat = (chapter - 1) % len(state["characters"]); leader = next(item for item in state["characters"] if item["seat"] == leader_seat)
            selected = ballot[f"ai:{leader_seat}"] if leader["ai"] else choices[leader["user_id"]]
        state, resolved = resolve_joint(state, selected); votes_public = ballot
        if state["status"] == "COMPLETED": session.status = "ended"; session.ended_at = utcnow()
        else: state, ai_scenes, counter = _play_ai_spotlights(state, seed, counter)
    _replace(db, session, row, state, counter, "CHAPTER_END" if resolved else "ACTION")
    append_event(db, session, "story.vote_received", {"user_id": actor.id, "chapter": chapter}, idempotency_key=f"story:vote:{chapter}:{actor.id}")
    if resolved:
        event = append_event(db, session, "story.chapter_committed", {**resolved, "votes": votes_public, "ending_vector": state["ending_vector"]}, idempotency_key=f"story:chapter:{chapter}")
        job_type = "story.ending_write" if state["status"] == "COMPLETED" else "story.scene_write"
        enqueue_job(db, module="shared_story", job_type=job_type, idempotency_key=f"story:prose:{event.id}", input_ref={"event_id": event.id, "content_kind": "ENDING" if state["status"] == "COMPLETED" else "CHAPTER"}, session_id=session.id, actor_id=actor.id, priority=2)
    # Yeni bölümün ilk sahneleri AI'a düştüyse onlar da bu turda işlenir.
    _commit_scenes(db, session, ai_scenes, actor)
    db.commit(); return story_view(db, session_id=session.id, actor=actor)
