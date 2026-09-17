"""Response assembly, output safety validation, and canned safe responses.

Implements Layer 4 output safety (PRD section 31) and the emergency response
policy (PRD section 32). The safety engine's verdict can OVERRIDE the LLM text.
"""
import re

from app.config import Settings, get_settings
from app.schemas.common import RiskLevel

DISCLAIMER = (
    "This is a health screening and guidance tool, not a diagnosis and not a "
    "substitute for a qualified healthcare professional."
)

# Phrases that assert a definitive diagnosis — softened before display (PRD section 4).
DIAGNOSIS_PATTERNS = [
    (re.compile(r"\byou have\b", re.IGNORECASE), "your symptoms can be associated with"),
    (re.compile(r"\byou are suffering from\b", re.IGNORECASE),
     "your symptoms can be associated with"),
    (re.compile(r"\byou've got\b", re.IGNORECASE), "your symptoms may be associated with"),
    (re.compile(r"\byou definitely have\b", re.IGNORECASE),
     "your symptoms may be associated with"),
    (re.compile(r"\bit is definitely\b", re.IGNORECASE), "it may be"),
    (re.compile(r"\bdiagnos(is|e|ed)\b", re.IGNORECASE), "assessment"),
]

# Unsafe prescription/dosage language — stripped (PRD sections 4, 31).
PRESCRIPTION_PATTERNS = [
    re.compile(r"\btake \d+\s?(mg|milligrams|tablets?|pills?)\b", re.IGNORECASE),
    re.compile(r"\bprescrib\w+\b", re.IGNORECASE),
]

RECOMMENDED_ACTION = {
    RiskLevel.EMERGENCY: "Seek emergency medical care immediately.",
    RiskLevel.URGENT: "Seek medical evaluation as soon as possible.",
    RiskLevel.ROUTINE: "Consider scheduling an appointment with a healthcare professional, especially if symptoms persist or worsen.",
    RiskLevel.SELF_CARE: "Monitor your symptoms and seek medical advice if they worsen or don't improve.",
    RiskLevel.UNKNOWN: "Let's gather a little more information to assess how urgent this may be.",
}

# Generic escalation warning signs shown for non-emergency levels (PRD section 35).
DEFAULT_WARNING_SIGNS = [
    "Symptoms suddenly become severe",
    "You develop weakness, numbness, or difficulty speaking",
    "You become confused or hard to wake",
    "You have difficulty breathing or chest pain",
    "You experience severe or persistent vomiting",
]


class OutputSafetyValidator:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def sanitize(self, text: str) -> str:
        for pattern, replacement in DIAGNOSIS_PATTERNS:
            text = pattern.sub(replacement, text)
        for pattern in PRESCRIPTION_PATTERNS:
            text = pattern.sub("[removed: specific medication advice]", text)
        return text

    def emergency_message(self) -> str:
        return (
            "The symptoms you've described could indicate a medical emergency. "
            f"Please seek emergency medical care now or contact {self.settings.emergency_number}. "
            "If possible, do not drive yourself if you are severely unwell, and don't wait to see if symptoms pass."
        )

    def self_harm_message(self) -> str:
        return (
            "I'm really sorry you're feeling this way, and I'm concerned about your safety. "
            "You deserve support right now. Please contact your local emergency number "
            f"({self.settings.emergency_number}) or a suicide/crisis helpline in your country "
            "immediately, and if you can, reach out to someone you trust to be with you. "
            "If you are in immediate danger, please call emergency services now."
        )


def recommended_action(risk: RiskLevel) -> str:
    return RECOMMENDED_ACTION.get(risk, RECOMMENDED_ACTION[RiskLevel.UNKNOWN])


def warning_signs_for(risk: RiskLevel) -> list[str]:
    if risk in (RiskLevel.EMERGENCY,):
        return []
    return list(DEFAULT_WARNING_SIGNS)
