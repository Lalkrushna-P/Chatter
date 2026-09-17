"""Feedback endpoint (PRD section 25)."""
from fastapi import APIRouter

from app.repositories.store import get_store
from app.schemas.chat import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/api", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    store = get_store()
    rec = store.add_feedback(req.conversation_id, req.rating, req.feedback_text)
    return FeedbackResponse(id=rec["id"])
