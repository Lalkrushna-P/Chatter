"""API-level guarantee: an unexpected bug anywhere in the pipeline must never
surface as a bare 500 mid health-screening — it should degrade to a safe,
generic reply instead (mirrors the existing LLM-failure fallback policy,
applied one layer up at the endpoint)."""
from fastapi.testclient import TestClient

from app.api import chat as chat_module
from app.main import app

client = TestClient(app)


def test_chat_endpoint_returns_200_on_normal_message():
    resp = client.post("/api/chat", json={"message": "I have a mild headache"})
    assert resp.status_code == 200
    assert resp.json()["message"]


def test_chat_endpoint_degrades_gracefully_instead_of_500(monkeypatch):
    async def boom(req):
        raise RuntimeError("simulated unexpected pipeline failure")

    monkeypatch.setattr(chat_module._manager, "handle_message", boom)

    resp = client.post("/api/chat", json={"message": "I have a headache"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_level"] == "unknown"
    assert "went wrong" in body["message"].lower()
    assert body["disclaimer"]
