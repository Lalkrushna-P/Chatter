"""Safety engine tests — the highest-priority test suite (PRD sections 37, 51).

False negatives on emergency symptoms are the most serious failure mode, so these
assertions focus on emergency/urgent detection.
"""
from app.schemas.common import RiskLevel
from app.services.safety_service import SafetyService

safety = SafetyService()


def test_chest_pain_with_shortness_of_breath_is_emergency():
    v = safety.evaluate_text("I have chest pain and difficulty breathing")
    assert v.risk_level == RiskLevel.EMERGENCY
    assert v.is_emergency


def test_stroke_signs_are_emergency():
    v = safety.evaluate_text(
        "I have a sudden severe headache and weakness on one side"
    )
    assert v.risk_level == RiskLevel.EMERGENCY


def test_thunderclap_headache_is_emergency():
    v = safety.evaluate_text("I have the worst headache of my life, it came on suddenly")
    assert v.risk_level == RiskLevel.EMERGENCY


def test_self_harm_detected():
    v = safety.evaluate_text("I want to kill myself")
    assert safety.has_self_harm(v)
    assert v.risk_level == RiskLevel.EMERGENCY


def test_mild_headache_is_not_emergency():
    v = safety.evaluate_text("I have a mild headache after working all day")
    assert v.risk_level != RiskLevel.EMERGENCY


def test_plain_fever_is_not_emergency():
    v = safety.evaluate_text("I have had a fever for two days")
    assert v.risk_level != RiskLevel.EMERGENCY


def test_sore_throat_then_breathing_escalates():
    v = safety.evaluate_conversation(
        ["I have a sore throat", "Now I have difficulty breathing"]
    )
    # Cumulative evaluation should surface the breathing red flag.
    assert v.risk_level in (RiskLevel.URGENT, RiskLevel.EMERGENCY)


def test_cumulative_red_flags_persist_across_turns():
    v = safety.evaluate_conversation(
        ["I have chest pain", "yes I am also short of breath"]
    )
    assert v.risk_level == RiskLevel.EMERGENCY


def test_pregnancy_flag_detected():
    v = safety.evaluate_text("I am 20 weeks pregnant and have abdominal pain")
    assert "pregnancy" in v.special_flags
