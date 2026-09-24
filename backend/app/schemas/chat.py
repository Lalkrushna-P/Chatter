"""Request/response schemas for the chat and assessment APIs."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import RiskLevel, Source, Symptom


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=4000)
    # Optional patient context (PRD section 33 — child/pregnancy safety)
    subject: Optional[str] = Field(
        default=None, description="'self' or 'someone_else'"
    )
    age: Optional[int] = Field(default=None, ge=0, le=120)
    is_pregnant: Optional[bool] = None
    # Previously uploaded reports (see /api/reports/upload) to ground this turn.
    report_ids: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    possible_categories: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    follow_up_question: Optional[str] = None
    sources: list[Source] = Field(default_factory=list)
    is_emergency: bool = False
    disclaimer: str = ""


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class AssessmentStartResponse(BaseModel):
    assessment_id: str
    conversation_id: str


class AssessmentSummary(BaseModel):
    """End-of-assessment summary (PRD section 35)."""

    assessment_id: str
    conversation_id: str
    symptoms: list[Symptom] = Field(default_factory=list)
    duration: Optional[str] = None
    severity: Optional[int] = None
    associated_symptoms: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    possible_explanations: list[str] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    seek_urgent_care_if: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    status: str = "active"


class FeedbackRequest(BaseModel):
    conversation_id: str
    rating: int = Field(ge=1, le=5)
    feedback_text: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: str
    status: str = "recorded"
