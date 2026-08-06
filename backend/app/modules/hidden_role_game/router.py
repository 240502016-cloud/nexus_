from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.hidden_role_game import schemas
from app.modules.hidden_role_game.service import create_game, game_view, get_active_game, submit_claim, submit_deduction, submit_vote


router = APIRouter(tags=["hidden-role-game"])

@router.post("/servers/{server_id}/hidden-role/sessions", response_model=schemas.HiddenGameView, status_code=201)
def post_game(server_id: int, payload: schemas.HiddenGameCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = create_game(db, server_id=server_id, actor=current_user, payload=payload, idempotency_key=idempotency_key); return game_view(db, session_id=session.id, actor=current_user)

@router.get("/servers/{server_id}/hidden-role/sessions/active", response_model=schemas.HiddenGameView | None)
def get_active(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_active_game(db, server_id=server_id, actor=current_user); return game_view(db, session_id=session.id, actor=current_user) if session else None

@router.get("/hidden-role/sessions/{session_id}", response_model=schemas.HiddenGameView)
def get_game(session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return game_view(db, session_id=session_id, actor=current_user)

@router.post("/hidden-role/sessions/{session_id}/claims", response_model=schemas.HiddenGameView)
def post_claim(session_id: str, payload: schemas.ClaimCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return submit_claim(db, session_id=session_id, actor=current_user, subject=payload.subject_option_id, proposition=payload.proposition, flavor=payload.flavor_text, token=payload.action_token, revision=payload.expected_revision)

@router.post("/hidden-role/sessions/{session_id}/votes", response_model=schemas.HiddenGameView)
def post_vote(session_id: str, payload: schemas.VoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return submit_vote(db, session_id=session_id, actor=current_user, option_id=payload.option_id, token=payload.action_token, revision=payload.expected_revision)

@router.post("/hidden-role/sessions/{session_id}/deductions", response_model=schemas.HiddenGameView)
def post_deduction(session_id: str, payload: schemas.DeductionCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)): return submit_deduction(db, session_id=session_id, actor=current_user, offices=payload.office_by_key, mandates=payload.mandate_by_key, token=payload.action_token, revision=payload.expected_revision)
