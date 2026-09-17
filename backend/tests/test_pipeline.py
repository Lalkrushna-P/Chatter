"""End-to-end pipeline tests against the PRD evaluation dataset (section 37).

These run fully offline (llm_provider=none, embedding_provider=local).
"""
import pytest

from app.schemas.chat import ChatRequest
from app.schemas.common import RiskLevel
from app.services.conversation_service import ConversationManager

manager = ConversationManager()


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
