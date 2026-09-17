"""Assessment endpoints (PRD section 25)."""
from fastapi import APIRouter, HTTPException

from app.repositories.store import get_store
from app.schemas.chat import AssessmentStartResponse, AssessmentSummary
from app.services.conversation_service import ConversationManager

router = APIRouter(prefix="/api/assessment", tags=["assessment"])
_manager = ConversationManager()


@router.post("/start", response_model=AssessmentStartResponse)
async def start_assessment() -> AssessmentStartResponse:
    store = get_store()
    conv = store.create_conversation(user_id=None)
    rec = store.upsert_assessment(
        conv["id"],
        {
            "symptoms": [],
            "questions_asked": [],
            "red_flags": [],
            "risk_level": "unknown",
            "possible_explanations": [],
            "status": "active",
        },
    )
    return AssessmentStartResponse(assessment_id=rec["id"], conversation_id=conv["id"])


@router.get("/{conversation_id}/summary", response_model=AssessmentSummary)
async def assessment_summary(conversation_id: str) -> AssessmentSummary:
    summary = _manager.build_summary(conversation_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return summary


@router.get("/{conversation_id}")
async def assessment_status(conversation_id: str) -> dict:
    store = get_store()
    rec = store.get_assessment_by_conversation(conversation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return {
        "conversation_id": conversation_id,
        "risk_level": rec.get("risk_level", "unknown"),
        "status": rec.get("status", "active"),
    }


@router.post("/{conversation_id}/end")
async def end_assessment(conversation_id: str) -> dict:
    store = get_store()
    rec = store.get_assessment_by_conversation(conversation_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    store.upsert_assessment(conversation_id, {"status": "completed"})
    store.update_conversation(conversation_id, status="completed")
    return {"conversation_id": conversation_id, "status": "completed"}
