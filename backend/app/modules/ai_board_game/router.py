from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.ai_board_game import schemas
from app.modules.ai_board_game.service import create_game, game_view, get_active_game, submit_action


router = APIRouter(tags=["ai-board-game"])


@router.post("/servers/{server_id}/board-game/sessions", response_model=schemas.BoardGameView, status_code=201)
def post_game(server_id: int, payload: schemas.BoardGameCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = create_game(db, server_id=server_id, actor=current_user, payload=payload, idempotency_key=idempotency_key)
    return game_view(db, session_id=session.id, actor=current_user)


@router.get("/servers/{server_id}/board-game/sessions/active", response_model=schemas.BoardGameView | None)
def get_active(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = get_active_game(db, server_id=server_id, actor=current_user)
    return game_view(db, session_id=session.id, actor=current_user) if session else None


@router.get("/board-game/sessions/{session_id}", response_model=schemas.BoardGameView)
def get_game(session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return game_view(db, session_id=session_id, actor=current_user)


@router.post("/board-game/sessions/{session_id}/actions", response_model=schemas.BoardGameView)
def post_action(session_id: str, payload: schemas.BoardActionCommand, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return submit_action(db, session_id=session_id, actor=current_user, action_id=payload.action_id, action_token=payload.action_token, expected_revision=payload.expected_revision, idempotency_key=idempotency_key)
