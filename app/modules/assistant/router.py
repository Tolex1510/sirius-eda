from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import rate_limit
from app.database import SessionLocal
from app.domain.entities import User
from app.domain.exceptions import DomainError
from app.http_errors import to_http_exception
from app.modules.assistant.ollama import OllamaModel
from app.modules.assistant.repository import SqlAssistantRepository
from app.modules.assistant.service import AssistantService

router = APIRouter()


def assistant_service():
    return AssistantService(SqlAssistantRepository(SessionLocal, settings.OLLAMA_EMBED_MODEL),
                            OllamaModel(settings.OLLAMA_URL, settings.OLLAMA_MODEL,
                                        settings.OLLAMA_EMBED_MODEL, settings.AI_TIMEOUT, host_header=settings.OLLAMA_HOST_HEADER))


class Question(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None


@router.post('/messages', dependencies=[Depends(rate_limit(10, 60))])
def ask(payload: Question, actor: User = Depends(get_current_user), service=Depends(assistant_service)):
    try:
        return service.ask(actor, payload.message, str(payload.conversation_id) if payload.conversation_id else None)
    except DomainError as exc:
        raise to_http_exception(exc)


@router.get('/conversations/{conversation_id}')
def history(conversation_id: UUID, actor: User = Depends(get_current_user), service=Depends(assistant_service)):
    try:
        return service.repository.history(actor, str(conversation_id))
    except DomainError as exc:
        raise to_http_exception(exc)
