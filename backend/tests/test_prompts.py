"""build_user_prompt must tell the LLM what's actually happening this turn —
otherwise it treats a context-question answer as a contentless new symptom
message, and/or invents its own follow-up question that conflicts with the
one the app deterministically appends afterward."""
from app.prompts.system_prompts import build_user_prompt
from app.schemas.common import RiskLevel


def _prompt(**overrides):
    base = dict(
        user_message="it's for my son",
        history=[],
        symptoms=[],
        risk_level=RiskLevel.SELF_CARE,
        red_flags=[],
        evidence=[],
        special_flags=[],
    )
    base.update(overrides)
    return build_user_prompt(**base)


def test_prompt_flags_context_answer_turns():
    prompt = _prompt(
        answered_context_question="Before we continue — is this assessment for you or for someone else?"
    )
    assert "answer to a question you asked last turn" in prompt
    assert "is this assessment for you or for someone else?" in prompt


def test_prompt_omits_context_note_on_normal_turns():
    prompt = _prompt(answered_context_question=None)
    assert "answer to a question you asked last turn" not in prompt


def test_prompt_tells_llm_not_to_invent_a_follow_up_when_one_is_planned():
    prompt = _prompt(pending_follow_up="What is the person's age?")
    assert "What is the person's age?" in prompt
    assert "Do NOT ask your own" in prompt


def test_prompt_allows_a_question_when_none_is_planned():
    prompt = _prompt(pending_follow_up=None)
    assert "may ask one clarifying question" in prompt
