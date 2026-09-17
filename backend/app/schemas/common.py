"""Shared enums and value objects used across the pipeline."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Four primary triage levels (PRD section 7 / 53)."""

    UNKNOWN = "unknown"
    EMERGENCY = "emergency"        # Level 1 — seek immediate care
    URGENT = "urgent"             # Level 2 — seek prompt medical care
    ROUTINE = "routine"           # Level 3 — schedule a consultation
    SELF_CARE = "self_care"       # Level 4 — monitor / self-care

    @property
    def rank(self) -> int:
        order = {
            "unknown": 0,
            "self_care": 1,
            "routine": 2,
            "urgent": 3,
            "emergency": 4,
        }
        return order[self.value]


class Symptom(BaseModel):
    """Structured symptom extracted from conversation (PRD FR-02)."""

    name: str
    location: Optional[str] = None
    severity: Optional[int] = Field(default=None, ge=0, le=10)
    duration: Optional[str] = None
    onset: Optional[str] = None
    frequency: Optional[str] = None
    trigger: Optional[str] = None
    relieving_factors: Optional[str] = None
    worsening_factors: Optional[str] = None
    associated_symptoms: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """A cited medical evidence source (PRD section 16)."""

    title: str
    source: Optional[str] = None
    source_url: Optional[str] = None
    category: Optional[str] = None
