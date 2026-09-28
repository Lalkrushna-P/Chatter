"""Chat endpoint (PRD section 25)."""
import traceback

from fastapi import APIRouter, HTTPException, Request

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import RiskLevel
from app.services.conversation_service import ConversationManager
from app.services.response_builder import DISCLAIMER, recommended_action
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api", tags=["chat"])
_manager = ConversationManager()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    enforce_rate_limit(request, authenticated=False)
    try:
        return await _manager.handle_message(req)
    except HTTPException:
        raise
    except Exception:
        # The safety engine + RAG evidence are the clinically important part of
        # this app (see README "Key architecture principle"); that guarantee is
        # only meaningful if an unrelated bug anywhere in the pipeline (state
        # persistence, a provider call, a parsing edge case) can never take the
        # whole response down with it. Log the real traceback server-side for
        # diagnosis, but never hand the user back a bare 500 mid health-screening.
        print("[chat] handle_message failed unexpectedly:")
        traceback.print_exc()
        return ChatResponse(
            conversation_id=req.conversation_id or "",
            message=(
                "Sorry, something went wrong on our end processing that message. "
                "Please try rephrasing or sending it again. If this is a medical "
                "emergency, please seek emergency care immediately."
            ),
            risk_level=RiskLevel.UNKNOWN,
            recommended_action=recommended_action(RiskLevel.UNKNOWN),
            disclaimer=DISCLAIMER,
        )
