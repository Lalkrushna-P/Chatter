"""build_query must fold in every extracted symptom attribute, not just
location/severity — this is what lets retrieval actually narrow as follow-up
answers accumulate detail across turns instead of repeating the first guess."""
from app.schemas.common import Symptom
from app.services.rag_service import RAGService

rag = RAGService()


def test_query_includes_onset_and_duration():
    symptom = Symptom(name="headache", onset="sudden", duration="2 hours")
    query = rag.build_query("my head hurts", [symptom])
    assert "sudden" in query
    assert "2 hours" in query


def test_query_includes_trigger_and_relieving_factors():
    symptom = Symptom(
        name="chest pain", trigger="exertion", relieving_factors="rest",
        worsening_factors="lying down",
    )
    query = rag.build_query("chest pain", [symptom])
    assert "exertion" in query
    assert "rest" in query
    assert "lying down" in query
