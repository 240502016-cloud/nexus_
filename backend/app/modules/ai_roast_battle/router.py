from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.ai_roast_battle import schemas
from app.modules.ai_roast_battle.models import RoastRound
from app.modules.ai_roast_battle.service import create_roast_session, round_to_dict, session_to_dict, start_next_round, submit_consent, update_profile, vote

router = APIRouter(tags=["ai-roast-battle"])

@router.put("/servers/{server_id}/roast-battle/profile/me", response_model=schemas.RoastProfileRead)
def put_profile(server_id: int, payload: schemas.RoastProfileUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return update_profile(db, server_id=server_id, actor=current_user, payload=payload)

@router.post("/servers/{server_id}/roast-battle/sessions", response_model=schemas.RoastSessionRead, status_code=201)
def post_session(server_id: int, payload: schemas.RoastSessionCreate, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return session_to_dict(db, create_roast_session(db, server_id=server_id, actor=current_user, payload=payload, idempotency_key=idempotency_key))

@router.post("/roast-battle/sessions/{session_id}/consent", response_model=schemas.RoastSessionRead)
def post_consent(session_id: str, payload: schemas.RoastConsentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return session_to_dict(db, submit_consent(db, session_id=session_id, actor=current_user, decision=payload.decision, consent_version=payload.consent_version))

@router.post("/roast-battle/sessions/{session_id}/rounds/next", response_model=schemas.RoastRoundRead, status_code=202)
def post_round(session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return round_to_dict(db, start_next_round(db, session_id=session_id, actor=current_user))

@router.get("/roast-battle/rounds/{round_id}", response_model=schemas.RoastRoundRead)
def get_round(round_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(RoastRound, round_id)
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Roast turu bulunamadı")
    from app.modules.ai_roast_battle.service import _roast_session
    from app.platform.sessions import ensure_session_player
    ensure_session_player(db, _roast_session(db, row.session_id), current_user.id)
    return round_to_dict(db, row)

@router.put("/roast-battle/candidates/{candidate_id}/vote")
def put_vote(candidate_id: str, payload: schemas.RoastVoteCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = vote(db, candidate_id=candidate_id, actor=current_user, vote_type=payload.vote)
    return {"candidate_id": row.candidate_id, "vote": row.vote_type, "score_contribution": row.score_contribution}

