"""Chat endpoint (PRD section 25)."""
from fastapi import APIRouter, Request

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.conversation_service import ConversationManager
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api", tags=["chat"])
_manager = ConversationManager()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    enforce_rate_limit(request, authenticated=False)
    return await _manager.handle_message(req)
