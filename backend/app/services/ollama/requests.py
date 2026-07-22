"""AI (Ollama) sohbet uç noktaları - model seçimi, sohbet geçmişi/context yönetimi,
token kullanım takibi.

Not: bu dosyanın adı `requests.py` (spec'teki services/ollama/requests yapısına göre);
üçüncü parti `requests` HTTP kütüphanesiyle çakışmaz çünkü bu modül her zaman
`app.services.ollama.requests` tam yoluyla içe aktarılır, asla çıplak `requests` olarak
değil - Python'ın mutlak import çözümlemesi (PEP 328) bunu garanti eder.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import get_current_user
from app.core.models import User
from app.database import get_db
from app.services.ollama.client import DEFAULT_SYSTEM_PROMPT, OllamaError, ollama_client
from app.services.ollama.models import (
    AiConversation,
    AiMessage,
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
    MessageRole,
    ModelInfo,
    UsageSummary,
)
from app.services.ollama.tokenizer import TokenUsage, record_usage, usage_summary_for_user

router = APIRouter(prefix="/ai", tags=["ai"])

# Küçük yerel modellerin bağlam penceresi sınırlı olduğu için (ör. varsayılan 4096
# token); sohbet büyüdükçe her isteğe sadece son N mesajı context olarak göndeririz.
MAX_CONTEXT_MESSAGES = 20


@router.get("/models", response_model=list[ModelInfo])
def list_models(current_user: User = Depends(get_current_user)):
    try:
        models = ollama_client.list_models()
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [ModelInfo(name=m["name"], size=m.get("size")) for m in models]


@router.post("/conversations", response_model=ConversationRead, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = AiConversation(
        user_id=current_user.id,
        model=payload.model or settings.ollama_default_model,
        title=payload.title,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(AiConversation)
        .filter(AiConversation.user_id == current_user.id)
        .order_by(AiConversation.id.desc())
        .all()
    )


def _get_owned_conversation(db: Session, conversation_id: int, user_id: int) -> AiConversation:
    conversation = db.get(AiConversation, conversation_id)
    if not conversation or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Sohbet bulunamadı")
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_owned_conversation(db, conversation_id, current_user.id)
    return conversation.messages


@router.post("/conversations/{conversation_id}/messages", response_model=MessageRead, status_code=201)
def send_message(
    conversation_id: int,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _get_owned_conversation(db, conversation_id, current_user.id)

    user_message = AiMessage(conversation_id=conversation.id, role=MessageRole.USER, content=payload.content)
    db.add(user_message)
    db.flush()

    # Context yönetimi: bu sohbetteki son N mesaj (yeni mesaj dahil), Ollama'ya
    # geçmiş olarak gönderilir. Sistem promptu her istekte eklenir ama DB'ye yazılmaz.
    history = conversation.messages[-MAX_CONTEXT_MESSAGES:]
    ollama_messages = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}] + [
        {"role": m.role.value, "content": m.content} for m in history
    ]

    try:
        response = ollama_client.chat(conversation.model, ollama_messages)
    except OllamaError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    reply_content = response.get("message", {}).get("content", "")
    assistant_message = AiMessage(
        conversation_id=conversation.id, role=MessageRole.ASSISTANT, content=reply_content
    )
    db.add(assistant_message)

    usage = TokenUsage.from_ollama_response(response)
    record_usage(
        db, user_id=current_user.id, conversation_id=conversation.id, model=conversation.model, usage=usage
    )

    db.commit()
    db.refresh(assistant_message)
    return assistant_message


@router.get("/usage", response_model=list[UsageSummary])
def get_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return usage_summary_for_user(db, current_user.id)
