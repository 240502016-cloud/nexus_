from fastapi import APIRouter,Depends,Header
from sqlalchemy.orm import Session
from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.modules.ai_escape_room import schemas
from app.modules.ai_escape_room.service import create_room,get_active_room,request_hint,room_view,submit_answer
router=APIRouter(tags=["ai-escape-room"])
@router.post("/servers/{server_id}/escape-room/sessions",response_model=schemas.EscapeView,status_code=201)
def post_room(server_id:int,payload:schemas.EscapeCreate,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=128),current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    s=create_room(db,server_id=server_id,actor=current_user,payload=payload,idempotency_key=idempotency_key);return room_view(db,session_id=s.id,actor=current_user)
@router.get("/servers/{server_id}/escape-room/sessions/active",response_model=schemas.EscapeView|None)
def get_active(server_id:int,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    s=get_active_room(db,server_id=server_id,actor=current_user);return room_view(db,session_id=s.id,actor=current_user) if s else None
@router.get("/escape-room/sessions/{session_id}",response_model=schemas.EscapeView)
def get_room(session_id:str,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):return room_view(db,session_id=session_id,actor=current_user)
@router.post("/escape-room/sessions/{session_id}/nodes/{node_id}/answers",response_model=schemas.EscapeAttemptResponse)
def post_answer(session_id:str,node_id:str,payload:schemas.EscapeAnswerCreate,idempotency_key:str=Header(alias="Idempotency-Key",min_length=8,max_length=128),current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):return submit_answer(db,session_id=session_id,node_id=node_id,actor=current_user,answer=payload.answer,token=payload.action_token,revision=payload.expected_revision,idempotency_key=idempotency_key)
@router.post("/escape-room/sessions/{session_id}/nodes/{node_id}/hints",response_model=schemas.EscapeView)
def post_hint(session_id:str,node_id:str,payload:schemas.EscapeHintCreate,current_user:User=Depends(get_current_user),db:Session=Depends(get_db)):return request_hint(db,session_id=session_id,node_id=node_id,actor=current_user,tier=payload.tier,token=payload.action_token,revision=payload.expected_revision)
