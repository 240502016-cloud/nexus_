from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.shared_story import schemas
from app.modules.shared_story.service import create_story, get_active_story, get_safety_profile, story_view, submit_action, submit_vote, update_safety_profile

router = APIRouter(tags=["shared-story"])

@router.get("/servers/{server_id}/shared-story/safety/me")
def get_safety(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return get_safety_profile(db, server_id=server_id, actor=current_user)
@router.put("/servers/{server_id}/shared-story/safety/me")
def put_safety(server_id: int, payload: schemas.StorySafetyUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return update_safety_profile(db, server_id=server_id, actor=current_user, payload=payload)
@router.post("/servers/{server_id}/shared-story/sessions", response_model=schemas.StoryView, status_code=201)
def post_story(server_id: int, payload: schemas.StoryCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = create_story(db, server_id=server_id, actor=current_user, payload=payload, idempotency_key=idempotency_key); return story_view(db, session_id=session.id, actor=current_user)
@router.get("/servers/{server_id}/shared-story/sessions/active", response_model=schemas.StoryView | None)
def get_active(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_active_story(db, server_id=server_id, actor=current_user); return story_view(db, session_id=session.id, actor=current_user) if session else None
@router.get("/shared-story/sessions/{session_id}", response_model=schemas.StoryView)
def get_story(session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return story_view(db, session_id=session_id, actor=current_user)
@router.post("/shared-story/sessions/{session_id}/actions", response_model=schemas.StoryView)
def post_action(session_id: str, payload: schemas.StoryActionCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return submit_action(db, session_id=session_id, actor=current_user, action_id=payload.action_id, token=payload.action_token, revision=payload.expected_revision, idempotency_key=idempotency_key)
@router.post("/shared-story/sessions/{session_id}/votes", response_model=schemas.StoryView)
def post_vote(session_id: str, payload: schemas.StoryVoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return submit_vote(db, session_id=session_id, actor=current_user, choice_id=payload.choice_id, token=payload.action_token, revision=payload.expected_revision)
