from __future__ import annotations
import json,time
from typing import Callable
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from app.config import settings
from app.core.models import User
from app.database import SessionLocal
from app.modules.party_lore.service import find_entries,record_lore_usage
from app.platform.events import append_event
from app.platform.models import AiRun,BackgroundJob,ExperienceEvent,ExperienceSession
from app.services.ollama.client import ollama_client

class HostOutput(BaseModel):
    model_config=ConfigDict(extra="forbid"); message:str=Field(min_length=1,max_length=500)
def process_escape_host_job(job_id:str,*,chat:Callable[...,dict]=ollama_client.chat)->dict:
    db=SessionLocal();lore=None
    try:
        job=db.get(BackgroundJob,job_id);event=db.get(ExperienceEvent,int(job.input_ref["event_id"])) if job else None;s=db.get(ExperienceSession,event.session_id) if event else None;actor=db.get(User,job.actor_id) if job and job.actor_id else None
        if not job or job.module!="ai_escape_room" or job.job_type!="escape.host_message" or not event or not s:raise ValueError("Unsupported escape host job")
        context={"event_type":event.event_type,"committed_payload":event.public_payload}
        if actor and (s.settings or {}).get("use_party_lore") and event.event_type in {"escape.room_started","escape.node_solved"}:
            entries=find_entries(db,server_id=s.server_id,actor=actor,module="ai_escape_room",participant_ids=[p.user_id for p in s.players],limit=1)
            if entries:lore=entries[0];context["optional_flavor"]={"title":lore.title,"summary":lore.summary[:180],"rule":"Çözüm, sayı, sıra, koordinat veya hint bilgisi yapma; adı ve bağlamı değiştir."}
    finally:db.close()
    system="NADİR-3 için kısa Türkçe AI Host'sun. Yalnız commit edilmiş sonucu anlat. Doğruluğa yalnız validator sonucu CORRECT diyorsa değin; çözüm/hint/private bilgi ekleme. JSON {\"message\":\"en çok 60 kelime\"}."
    started=time.monotonic();response=chat(settings.escape_room_host_model,[{"role":"system","content":system},{"role":"user","content":json.dumps(context,ensure_ascii=False)}],timeout=settings.escape_room_host_timeout_seconds,options={"temperature":.3,"num_predict":130})
    try:output=HostOutput.model_validate(json.loads(response["message"]["content"]))
    except (KeyError,TypeError,json.JSONDecodeError,ValidationError) as exc:raise ValueError("INVALID_ESCAPE_HOST_OUTPUT") from exc
    db=SessionLocal()
    try:
        event=db.get(ExperienceEvent,int(job.input_ref["event_id"]));s=db.get(ExperienceSession,event.session_id);actor=db.get(User,job.actor_id) if job.actor_id else None
        append_event(db,s,"escape.host_message_ready",{"source_event_id":event.id,"text":output.message,"lore_reference_ids":[lore.id] if lore else []},idempotency_key=f"escape:host-ready:{event.id}")
        if lore and actor:record_lore_usage(db,entry=lore,actor=actor,module="ai_escape_room",request_id=f"escape:{event.id}",context={"event_type":event.event_type})
        db.add(AiRun(job_id=job_id,logical_profile="escape_room_host",provider="ollama-gateway",model=str(response.get("model") or settings.escape_room_host_model),prompt_version="escape-host-v1",latency_ms=int((time.monotonic()-started)*1000),status="succeeded"));db.commit();return {"message":output.message}
    finally:db.close()
