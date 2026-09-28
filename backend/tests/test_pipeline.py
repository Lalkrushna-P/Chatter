"""End-to-end pipeline tests against the PRD evaluation dataset (section 37).

These run fully offline (llm_provider=none, embedding_provider=local).
"""
import pytest

from app.schemas.chat import ChatRequest
from app.schemas.common import RiskLevel, Symptom
from app.services.conversation_service import ConversationManager, _age_descriptor
from app.services.symptom_service import TREND_QUESTION

manager = ConversationManager()


async def _advance_to_trend_question(first_message: str) -> tuple[str, object]:
    """Drive a conversation forward, answering whatever follow-up question
    comes back, until TREND_QUESTION is asked (or give up after a few turns).
    Returns (conversation_id, last_response).
    """
    resp = await manager.handle_message(ChatRequest(message=first_message))
    cid = resp.conversation_id
    guard = 0
    while (
        resp.follow_up_question
        and resp.follow_up_question != TREND_QUESTION
        and guard < 8
    ):
        q = resp.follow_up_question.lower()
        if "for you or for someone else" in q:
            answer = "it is for me"
        elif "how many nights" in q or "0-10" in q:
            answer = "severity 6 out of 10, for 3 days"
        elif "other symptoms" in q:
            answer = "no other symptoms"
        else:
            answer = "not sure"
        resp = await manager.handle_message(
            ChatRequest(conversation_id=cid, message=answer)
        )
        guard += 1
    return cid, resp


@pytest.mark.asyncio
async def test_tc002_sudden_headache_weakness_emergency():
    resp = await manager.handle_message(
        ChatRequest(message="I have sudden severe headache and weakness on one side")
    )
    assert resp.risk_level == RiskLevel.EMERGENCY
    assert resp.is_emergency
    assert "emergency" in resp.message.lower()


@pytest.mark.asyncio
async def test_tc003_chest_pain_breathing_emergency():
    resp = await manager.handle_message(
        ChatRequest(message="I have chest pain and difficulty breathing")
    )
    assert resp.risk_level == RiskLevel.EMERGENCY


@pytest.mark.asyncio
async def test_tc001_mild_headache_low_risk():
    resp = await manager.handle_message(
        ChatRequest(message="I have a mild headache after working all day")
    )
    assert resp.risk_level != RiskLevel.EMERGENCY
    assert resp.disclaimer


@pytest.mark.asyncio
async def test_tc004_fever_gets_follow_up():
    resp = await manager.handle_message(
        ChatRequest(message="I have fever for two days")
    )
    assert resp.follow_up_question is not None


@pytest.mark.asyncio
async def test_conversation_state_persists():
    first = await manager.handle_message(ChatRequest(message="I have a headache"))
    cid = first.conversation_id
    second = await manager.handle_message(
        ChatRequest(conversation_id=cid, message="it is 8/10 severity")
    )
    assert second.conversation_id == cid
    summary = manager.build_summary(cid)
    assert summary is not None
    assert any(s.name == "headache" for s in summary.symptoms)


@pytest.mark.asyncio
async def test_no_definitive_diagnosis_language():
    resp = await manager.handle_message(
        ChatRequest(message="I have a headache and mild nausea")
    )
    assert "you have migraine" not in resp.message.lower()


@pytest.mark.asyncio
async def test_context_answer_gets_acknowledged_not_ignored():
    """Answering "who is this for" should visibly react to that answer and
    move on to the next question — not treat the answer as a fresh, contentless
    symptom message and repeat/ignore what was just said.
    """
    first = await manager.handle_message(ChatRequest(message="I have a headache"))
    cid = first.conversation_id
    assert "for you or for someone else" in first.follow_up_question.lower()

    second = await manager.handle_message(
        ChatRequest(conversation_id=cid, message="it's for my son")
    )
    assert "someone else" in second.message.lower()
    assert second.follow_up_question != first.follow_up_question


@pytest.mark.asyncio
async def test_bare_followup_answer_still_updates_symptom_detail():
    """A follow-up reply that doesn't restate the symptom name (e.g. just
    "severity is 8 out of 10, lasted 2 days") must still narrow the tracked
    symptom detail — this is the core of "the result isn't narrowing":
    extract() alone finds no symptom in that message and would otherwise
    silently drop the answer.
    """
    first = await manager.handle_message(ChatRequest(message="I have a headache"))
    cid = first.conversation_id
    await manager.handle_message(ChatRequest(conversation_id=cid, message="it is for me"))
    await manager.handle_message(
        ChatRequest(conversation_id=cid, message="severity is 8 out of 10, lasted 2 days")
    )
    summary = manager.build_summary(cid)
    assert summary.severity == 8
    assert "2 day" in (summary.duration or "")


@pytest.mark.asyncio
async def test_trend_worse_floors_risk_and_names_a_specialist():
    cid, resp = await _advance_to_trend_question("I can't sleep")
    assert resp.follow_up_question == TREND_QUESTION

    final = await manager.handle_message(
        ChatRequest(conversation_id=cid, message="it is getting worse")
    )
    assert final.risk_level.rank >= RiskLevel.URGENT.rank
    action = final.recommended_action.lower()
    assert "worse" in action
    assert "as soon as possible" in action


@pytest.mark.asyncio
async def test_trend_same_needs_attention_worse_never_downgrades_emergency():
    cid, resp = await _advance_to_trend_question("I have a headache")
    assert resp.follow_up_question == TREND_QUESTION

    final = await manager.handle_message(
        ChatRequest(conversation_id=cid, message="staying about the same")
    )
    assert final.risk_level.rank >= RiskLevel.ROUTINE.rank
    assert "needs attention" in final.recommended_action.lower()


@pytest.mark.asyncio
async def test_trend_better_suggests_continuing_current_care():
    cid, resp = await _advance_to_trend_question("I have a mild headache")
    assert resp.follow_up_question == TREND_QUESTION

    final = await manager.handle_message(
        ChatRequest(conversation_id=cid, message="it is getting better")
    )
    assert "continue your current care" in final.recommended_action.lower()


def test_possible_explanations_narrows_as_more_is_known():
    """Same evidence, more known detail -> a shorter, more focused list —
    this is what makes the differential actually narrow turn over turn
    instead of showing the same handful of titles regardless of what's
    been answered.
    """
    from dataclasses import dataclass

    @dataclass
    class _FakeEvidence:
        title: str
        content: str = ""

    evidence = [_FakeEvidence(title=f"Condition {i}") for i in range(5)]
    bare = manager._possible_explanations(
        evidence, [Symptom(name="headache")], {}
    )
    detailed = manager._possible_explanations(
        evidence,
        [Symptom(name="headache", severity=6, duration="2 days", onset="sudden")],
        {"age": 30, "trend": "worse"},
    )
    assert len(bare) == 5
    assert 2 <= len(detailed) < len(bare)


def test_age_descriptor_bands():
    assert "infant" in _age_descriptor(0)
    assert "child" in _age_descriptor(6)
    assert "adolescent" in _age_descriptor(15)
    assert "elderly" in _age_descriptor(70)
    assert "adult" in _age_descriptor(35)
    assert _age_descriptor(None) == ""


def test_consume_context_answer_nulls_key_instead_of_removing():
    """SupabaseStore.upsert_assessment merges each save onto a freshly re-fetched
    copy of the existing row, so a key that's merely *absent* from this turn's
    state dict (e.g. via dict.pop()) doesn't get cleared in storage — the stale
    value silently wins the merge again next turn. The key must stay present,
    set to None, so the merge actually overwrites it.
    """
    state = {"awaiting_context": "subject"}
    manager._consume_context_answer(state, "it is for me")
    assert "awaiting_context" in state
    assert state["awaiting_context"] is None
