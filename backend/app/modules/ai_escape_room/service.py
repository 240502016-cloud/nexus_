from __future__ import annotations
import hashlib, hmac, re, unicodedata
from datetime import timedelta, timezone
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.config import settings
from app.core.authz import ensure_server_member
from app.core.models import Server, User
from app.modules.ai_escape_room.content import content_for, rules_version_for
from app.modules.ai_escape_room.models import EscapeAttempt, EscapeFinalAssistConsent, EscapeHintDelivery, EscapePrivateConsole, EscapeRoomState, EscapeSimultaneousSubmission
from app.modules.ai_escape_room.schemas import EscapeCreate
from app.platform.crypto import decrypt_json, encrypt_json
from app.platform.events import append_event
from app.platform.jobs import enqueue_job
from app.platform.models import ExperienceEvent, ExperienceSession, ExperienceSessionPlayer, utcnow
from app.platform.sessions import ai_seats, create_active_session, ensure_session_access, ensure_session_player

def _seed(session_id: str) -> bytes: return hmac.new(settings.core_api_secret_key.encode(), f"escape:{session_id}".encode(), hashlib.sha256).digest()
def _token(session_id: str, user_id: int, revision: int, operation: str, node_id: str) -> str: return hmac.new(settings.core_api_secret_key.encode(), f"escape:{session_id}:{user_id}:{revision}:{operation}:{node_id}".encode(), hashlib.sha256).hexdigest()
def _normalize(value: str) -> str: return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).strip().upper().replace("İ", "I"))

def _session(db: Session, session_id: str, *, lock: bool=False) -> ExperienceSession:
    q=db.query(ExperienceSession).filter_by(id=session_id); q=q.with_for_update() if lock else q; s=q.first()
    if not s or s.module_type!="ai_escape_room": raise HTTPException(404,"NADİR-3 oturumu bulunamadı")
    return s
def _state(db: Session, session_id: str, *, lock: bool=False) -> EscapeRoomState:
    q=db.query(EscapeRoomState).filter(EscapeRoomState.session_id==session_id, EscapeRoomState.is_current.is_(True)); q=q.with_for_update() if lock else q; row=q.first()
    if not row: raise HTTPException(409,"Escape Room durumu hazır değil")
    return row
def _content(s: ExperienceSession) -> dict:
    """Oturumun bulmaca seti. Koltuk sayısı odayı kurarken sabitlenir."""
    return content_for((s.settings or {}).get("rules_version", "nadir3-v1"))
def _ai_roles(engine: dict) -> set[str]:
    """AI'ın tuttuğu konsolların rolleri. İnsan oyuncular bu rollerin bulmacalarını da gönderebilir."""
    return {console["role"] for console in engine.get("ai_consoles", {}).values()}
def _can_submit(owner_role: str, actor_role: str, ai_roles: set[str]) -> bool:
    return owner_role in {"ANY", "ALL", actor_role} or owner_role in ai_roles
def _console(db: Session, session_id: str, user_id: int) -> tuple[EscapePrivateConsole,dict]:
    row=db.get(EscapePrivateConsole,{"session_id":session_id,"user_id":user_id})
    if not row: raise HTTPException(409,"Özel konsol bulunamadı")
    return row,decrypt_json(row.encrypted_payload,aad=f"escape-console:{session_id}:{user_id}")
def _replace(db:Session,s:ExperienceSession,row:EscapeRoomState,public:dict,engine:dict,reason:str)->None:
    row.is_current=False;s.revision+=1;db.add(EscapeRoomState(session_id=s.id,revision=s.revision,public_state=public,engine_ciphertext=encrypt_json(engine,aad=f"escape-state:{s.id}:{s.revision}"),rng_commitment=row.rng_commitment))

def create_room(db:Session,*,server_id:int,actor:User,payload:EscapeCreate,idempotency_key:str)->ExperienceSession:
    # Koltuk sayısı içerik setini belirler: iki koltuk iki rollü sete, üç koltuk
    # (üç insan ya da iki insan + AI) NADİR-3'e gider.
    rules_version=rules_version_for(len(payload.player_ids)+payload.ai_players)
    s=create_active_session(db,server_id=server_id,module_type="ai_escape_room",owner=actor,player_ids=payload.player_ids,idempotency_key=idempotency_key,settings={"timer_mode":payload.timer_mode,"use_party_lore":payload.use_party_lore,"rules_version":rules_version},ai_seat_count=payload.ai_players,min_seats=2,max_seats=3)
    if db.query(EscapeRoomState).filter_by(session_id=s.id).first(): return s
    content=_content(s); roles=content["roles"]; puzzles=content["puzzles"]; clues=content["clues"]
    players=sorted(s.players,key=lambda x:x.seat)
    for player in players:
        role=roles[player.seat]; payload_private={"role":role,"clues":clues[role],"ability_available":True}
        db.add(EscapePrivateConsole(session_id=s.id,user_id=player.user_id,role=role,encrypted_payload=encrypt_json(payload_private,aad=f"escape-console:{s.id}:{player.user_id}")))
    # AI konsolu escape_private_consoles tablosuna yazılamaz (user_id users.id'ye FK'dir),
    # bu yüzden zaten şifreli olan motor durumunda tutulur.
    ai_consoles={f"ai:{seat}":{"role":roles[seat],"clues":clues[roles[seat]],"ability_available":True} for seat in ai_seats(s)}
    public={"status":"ACTIVE","node_status":{node:("AVAILABLE" if node=="E0" else "LOCKED") for node in puzzles},"inventory":[],"assisted":False,"max_hint_tier":0,"result":None}
    engine={"template_version":rules_version,"ai_consoles":ai_consoles}; seed=_seed(s.id); commitment=hashlib.sha256(seed).hexdigest()
    db.add(EscapeRoomState(session_id=s.id,revision=s.revision,public_state=public,engine_ciphertext=encrypt_json(engine,aad=f"escape-state:{s.id}:{s.revision}"),rng_commitment=commitment))
    event=append_event(db,s,"escape.room_started",{"room":"NADİR-3","timer_mode":payload.timer_mode,"rules_version":rules_version,"ai_seats":ai_seats(s),"rng_commitment":commitment},idempotency_key="escape:start")
    enqueue_job(db,module="ai_escape_room",job_type="escape.host_message",idempotency_key=f"escape:host:{event.id}",input_ref={"event_id":event.id},session_id=s.id,actor_id=actor.id,priority=1);db.commit();return _session(db,s.id)

def get_active_room(db:Session,*,server_id:int,actor:User)->ExperienceSession|None:
    server=db.get(Server,server_id)
    if not server: raise HTTPException(404,"Sunucu bulunamadı")
    ensure_server_member(db,server,actor)
    return db.query(ExperienceSession).join(ExperienceSessionPlayer,ExperienceSessionPlayer.session_id==ExperienceSession.id).filter(ExperienceSession.server_id==server_id,ExperienceSession.module_type=="ai_escape_room",ExperienceSession.status=="active",ExperienceSessionPlayer.user_id==actor.id).order_by(ExperienceSession.updated_at.desc()).first()

def _elapsed(s:ExperienceSession)->int:
    start=s.started_at or s.created_at; now=utcnow()
    if start.tzinfo is None: start=start.replace(tzinfo=timezone.utc)
    return max(0,int((now-start).total_seconds()))
def _is_overtime(s:ExperienceSession,elapsed:int)->bool:
    limit={"STANDARD_45":2700,"CHALLENGE_30":1800}.get((s.settings or {}).get("timer_mode"));return bool(limit and elapsed>limit)
def room_view(db:Session,*,session_id:str,actor:User)->dict:
    s=_session(db,session_id);ensure_session_access(db,s,actor);ensure_session_player(db,s,actor.id);row=_state(db,s.id);public=row.public_state; console_row,private=_console(db,s.id,actor.id)
    content=_content(s); puzzles=content["puzzles"]; roles=content["roles"]
    engine=decrypt_json(row.engine_ciphertext,aad=f"escape-state:{s.id}:{row.revision}"); ai_consoles=engine.get("ai_consoles",{}); ai_roles=_ai_roles(engine)
    elapsed=_elapsed(s); overtime=_is_overtime(s,elapsed); available={node for node,status in public["node_status"].items() if status in {"AVAILABLE","IN_PROGRESS"}}
    nodes=[]
    for node_id,puzzle in puzzles.items():
        status=public["node_status"][node_id]; already_submitted = db.query(EscapeSimultaneousSubmission).filter_by(session_id=s.id,node_id=node_id,user_id=actor.id).first() is not None
        eligible=status=="AVAILABLE" and _can_submit(puzzle["owner_role"],console_row.role,ai_roles) and not already_submitted
        nodes.append({"id":node_id,"title":puzzle["title"],"kind":puzzle["kind"],"status":status,"dependencies":puzzle["dependencies"],"answer_type":puzzle["answer_type"],"answer_format":puzzle["answer_format"],"owner_role":puzzle["owner_role"],"required":puzzle["required"],"attempt_count":db.query(EscapeAttempt).filter_by(session_id=s.id,node_id=node_id).count(),"submitted_count":db.query(EscapeSimultaneousSubmission).filter_by(session_id=s.id,node_id=node_id).count()+sum(1 for key in ai_consoles if key in public.get("ai_submissions",{}).get(node_id,[])),"submit_token":_token(s.id,actor.id,row.revision,"SUBMIT",node_id) if eligible else None,"hint_token":_token(s.id,actor.id,row.revision,"HINT",node_id) if status=="AVAILABLE" else None})
    names={p.user_id:p.user.display_name or p.user.username for p in s.players}
    players=[{"user_id":p.user_id,"display_name":names[p.user_id],"seat":p.seat,"role":roles[p.seat],"ai":False} for p in sorted(s.players,key=lambda x:x.seat)]
    players+=[{"user_id":None,"display_name":f"NADİR yardımcı konsolu ({console['role']})","seat":int(key.split(':')[1]),"role":console["role"],"ai":True} for key,console in ai_consoles.items()]
    players.sort(key=lambda item:item["seat"])
    # AI konsolu takım arkadaşı gibi davranır: açık düğümler için kendi özel
    # ipuçlarını paylaşır, ama bulmacayı insanların yerine çözmez.
    ai_console_view=[{"role":console["role"],"clues":{key:value for key,value in console["clues"].items() if key in available}} for console in ai_consoles.values()]
    hints=[{"node_id":h.node_id,"tier":h.tier,"text":h.text} for h in db.query(EscapeHintDelivery).filter_by(session_id=s.id,user_id=actor.id).order_by(EscapeHintDelivery.created_at).all()]
    msgs=[e.public_payload for e in db.query(ExperienceEvent).filter_by(session_id=s.id,event_type="escape.host_message_ready").order_by(ExperienceEvent.sequence).all()]
    return {"session_id":s.id,"server_id":s.server_id,"status":public["status"],"revision":row.revision,"rules_version":(s.settings or {}).get("rules_version","nadir3-v1"),"seat_count":len(players),"timer_mode":(s.settings or {}).get("timer_mode","RELAXED"),"elapsed_seconds":elapsed,"overtime":overtime,"nodes":nodes,"players":players,"ai_consoles":ai_console_view,"shared_inventory":public["inventory"],"own_private":{"role":private["role"],"clues":{key:value for key,value in private["clues"].items() if key in available},"ability_available":private["ability_available"]},"hints":hints,"host_messages":msgs,"result":public["result"],"rng_commitment":row.rng_commitment}

def _authorized(row:EscapeRoomState,s:ExperienceSession,actor:User,node_id:str,operation:str,token:str,revision:int)->None:
    if row.revision!=revision: raise HTTPException(409,detail={"message":"Oda revizyonu güncel değil","current_revision":row.revision})
    if row.public_state["node_status"].get(node_id)!="AVAILABLE": raise HTTPException(409,"Bulmaca erişilebilir değil")
    if not hmac.compare_digest(_token(s.id,actor.id,revision,operation,node_id),token): raise HTTPException(409,"Bulmaca yetkisi geçersiz veya süresi dolmuş")
def _validate(puzzles:dict,node_id:str,role:str,answer:str)->bool:
    expected=puzzles[node_id]["solution"]
    if isinstance(expected,dict): expected=expected[role]
    return hmac.compare_digest(_normalize(answer),_normalize(str(expected)))
def _unlock(puzzles:dict,public:dict)->None:
    changed=True
    while changed:
        changed=False
        for node_id,puzzle in puzzles.items():
            if public["node_status"][node_id]=="LOCKED" and all(public["node_status"][dep]=="SOLVED" for dep in puzzle["dependencies"]): public["node_status"][node_id]="AVAILABLE";changed=True
def _complete_result(s:ExperienceSession,public:dict,elapsed:int)->dict:
    optional=public["node_status"]["O1"]=="SOLVED";mode=(s.settings or {}).get("timer_mode","RELAXED"); overtime=_is_overtime(s,elapsed)
    if public["assisted"]: grade="ASSISTED"
    elif overtime: grade="C"
    elif public["max_hint_tier"]>=3: grade="B"
    elif mode=="RELAXED": grade="A"
    elif optional and public["max_hint_tier"]<=1 and elapsed<=({"STANDARD_45":2700,"CHALLENGE_30":1800}[mode]*.75): grade="S"
    else: grade="A"
    return {"grade":grade,"elapsed_seconds":elapsed,"overtime":overtime,"assisted":public["assisted"],"optional_solved":optional,"max_hint_tier":public["max_hint_tier"]}
def _solve(db:Session,s:ExperienceSession,row:EscapeRoomState,public:dict,engine:dict,node_id:str,actor_id:int,assisted:bool=False)->ExperienceEvent:
    puzzles=_content(s)["puzzles"]
    public["node_status"][node_id]="SOLVED";grant=puzzles[node_id]["grant"]
    if grant and grant not in public["inventory"]: public["inventory"].append(grant)
    if assisted: public["assisted"]=True
    _unlock(puzzles,public)
    if node_id=="F1": public["status"]="COMPLETED";public["result"]=_complete_result(s,public,_elapsed(s));s.status="ended";s.ended_at=utcnow()
    _replace(db,s,row,public,engine,"SOLVE")
    event=append_event(db,s,"escape.node_solved",{"node_id":node_id,"title":puzzles[node_id]["title"],"grant":grant,"assisted":assisted,"result":public["result"]},idempotency_key=f"escape:solved:{node_id}")
    enqueue_job(db,module="ai_escape_room",job_type="escape.host_message",idempotency_key=f"escape:host:{event.id}",input_ref={"event_id":event.id},session_id=s.id,actor_id=actor_id,priority=1);return event

def submit_answer(db:Session,*,session_id:str,node_id:str,actor:User,answer:str,token:str,revision:int,idempotency_key:str)->dict:
    s=_session(db,session_id,lock=True);ensure_session_access(db,s,actor);ensure_session_player(db,s,actor.id);prior=db.query(EscapeAttempt).filter_by(session_id=s.id,user_id=actor.id,idempotency_key=idempotency_key).first()
    if prior:return {"validator_result":prior.result,"node_id":node_id,"view":room_view(db,session_id=s.id,actor=actor)}
    row=_state(db,s.id,lock=True);_authorized(row,s,actor,node_id,"SUBMIT",token,revision);console,_private=_console(db,s.id,actor.id)
    puzzles=_content(s)["puzzles"];roles=_content(s)["roles"];puzzle=puzzles.get(node_id)
    if not puzzle:raise HTTPException(404,"Bulmaca bulunamadı")
    engine_peek=decrypt_json(row.engine_ciphertext,aad=f"escape-state:{s.id}:{row.revision}")
    # AI'ın tuttuğu konsola ait bulmacaları insanlar gönderebilir: AI bilgi paylaşır,
    # çözümü oyuncular yapar. Aksi hâlde o düğüm hiç gönderilemezdi.
    if not _can_submit(puzzle["owner_role"],console.role,_ai_roles(engine_peek)):raise HTTPException(403,"Bu konsol bulmacayı gönderemez")
    answer_hash=hashlib.sha256(_normalize(answer).encode()).hexdigest();duplicate=db.query(EscapeAttempt).filter_by(session_id=s.id,node_id=node_id,user_id=actor.id,answer_hash=answer_hash).first()
    if duplicate:return {"validator_result":"DUPLICATE","node_id":node_id,"view":room_view(db,session_id=s.id,actor=actor)}
    recent=db.query(EscapeAttempt).filter(EscapeAttempt.session_id==s.id,EscapeAttempt.node_id==node_id,EscapeAttempt.user_id==actor.id,EscapeAttempt.created_at>=utcnow()-timedelta(seconds=30)).order_by(EscapeAttempt.created_at.desc()).limit(5).all()
    if len(recent)>=5: raise HTTPException(429,"Bu bulmaca için kısa süreli deneme sınırına ulaşıldı")
    correct=_validate(puzzles,node_id,console.role,answer);result="CORRECT" if correct else "INCORRECT";attempt=EscapeAttempt(session_id=s.id,node_id=node_id,user_id=actor.id,idempotency_key=idempotency_key,answer_hash=answer_hash,result=result,state_revision=revision);db.add(attempt);db.flush();public={**row.public_state};engine=decrypt_json(row.engine_ciphertext,aad=f"escape-state:{s.id}:{row.revision}")
    if puzzle["answer_type"]=="SIMULTANEOUS_INPUT" and correct:
        db.add(EscapeSimultaneousSubmission(session_id=s.id,node_id=node_id,user_id=actor.id,encrypted_value=encrypt_json({"value":_normalize(answer)},aad=f"escape-submit:{s.id}:{node_id}:{actor.id}"),value_hash=answer_hash));db.flush()
        human_count=db.query(EscapeSimultaneousSubmission).filter_by(session_id=s.id,node_id=node_id).count()
        ai_keys=list(engine.get("ai_consoles",{}))
        submitted=dict(public.get("ai_submissions",{}))
        # İnsan konsollarının hepsi girdikten sonra AI kendi kodunu aynı anda gönderir.
        if ai_keys and human_count==len(roles)-len(ai_keys): submitted[node_id]=ai_keys;public["ai_submissions"]=submitted
        total=human_count+len(submitted.get(node_id,[]))
        if total==len(roles):_solve(db,s,row,public,engine,node_id,actor.id)
        else:_replace(db,s,row,public,engine,"SUBMISSION");append_event(db,s,"escape.simultaneous_received",{"node_id":node_id,"submitted_count":total,"required_count":len(roles)},idempotency_key=f"escape:sim:{node_id}:{actor.id}")
    elif correct:_solve(db,s,row,public,engine,node_id,actor.id)
    else:
        _replace(db,s,row,public,engine,"ATTEMPT");event=append_event(db,s,"escape.answer_checked",{"node_id":node_id,"validator_result":"INCORRECT"},idempotency_key=f"escape:attempt:{attempt.id}");enqueue_job(db,module="ai_escape_room",job_type="escape.host_message",idempotency_key=f"escape:host:{event.id}",input_ref={"event_id":event.id},session_id=s.id,actor_id=actor.id,priority=0)
    db.commit();return {"validator_result":result,"node_id":node_id,"view":room_view(db,session_id=s.id,actor=actor)}

def request_hint(db:Session,*,session_id:str,node_id:str,actor:User,tier:int,token:str,revision:int)->dict:
    s=_session(db,session_id,lock=True);ensure_session_access(db,s,actor);ensure_session_player(db,s,actor.id);row=_state(db,s.id,lock=True);_authorized(row,s,actor,node_id,"HINT",token,revision);attempts=db.query(EscapeAttempt).filter_by(session_id=s.id,node_id=node_id).count();required={1:0,2:2,3:4,4:5}[tier]
    if attempts<required:raise HTTPException(409,f"Tier {tier} için en az {required} benzersiz başarısız deneme gerekli")
    existing=db.query(EscapeHintDelivery).filter_by(session_id=s.id,node_id=node_id,user_id=actor.id,tier=tier).first()
    if existing:return room_view(db,session_id=s.id,actor=actor)
    public={**row.public_state};engine=decrypt_json(row.engine_ciphertext,aad=f"escape-state:{s.id}:{row.revision}")
    content=_content(s);puzzles=content["puzzles"];roles=content["roles"];ai_count=len(engine.get("ai_consoles",{}))
    if tier<4:
        text=puzzles[node_id]["hints"][tier-1];db.add(EscapeHintDelivery(session_id=s.id,node_id=node_id,user_id=actor.id,tier=tier,text=text));public["max_hint_tier"]=max(public["max_hint_tier"],tier);_replace(db,s,row,public,engine,"HINT");append_event(db,s,"escape.hint_delivered",{"node_id":node_id,"tier":tier,"audience_user_id":actor.id},audience=f"USER:{actor.id}",idempotency_key=f"escape:hint:{node_id}:{actor.id}:{tier}")
    else:
        db.add(EscapeFinalAssistConsent(session_id=s.id,node_id=node_id,user_id=actor.id));db.flush()
        # Final yardımı tüm konsolların onayını ister; AI koltuğu insanlar onayladıktan
        # sonra kendi onayını verir, karar yine oyuncularındır.
        human_consents=db.query(EscapeFinalAssistConsent).filter_by(session_id=s.id,node_id=node_id).count()
        count=human_consents+(ai_count if human_consents==len(roles)-ai_count else 0)
        if count==len(roles):_solve(db,s,row,public,engine,node_id,actor.id,assisted=True)
        else:_replace(db,s,row,public,engine,"ASSIST_CONSENT");append_event(db,s,"escape.final_assist_consent",{"node_id":node_id,"consent_count":count,"required_count":len(roles)},idempotency_key=f"escape:assist:{node_id}:{actor.id}")
    db.commit();return room_view(db,session_id=s.id,actor=actor)
