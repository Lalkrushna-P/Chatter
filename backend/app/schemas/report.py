"""Request/response schemas for medical-report upload & analysis."""
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import RiskLevel, Source


class LabValueOut(BaseModel):
    name: str
    value: float
    unit: str
    reference_low: float
    reference_high: float
    flag: str  # "low" | "normal" | "high"


class ReportAnalysis(BaseModel):
    report_id: str
    conversation_id: Optional[str] = None
    filename: str
    summary: str
    flagged_values: list[LabValueOut] = Field(default_factory=list)
    possible_categories: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    recommended_action: Optional[str] = None
    sources: list[Source] = Field(default_factory=list)
    disclaimer: str = ""
    status: str = "completed"


class ReportUploadResponse(ReportAnalysis):
    pass
