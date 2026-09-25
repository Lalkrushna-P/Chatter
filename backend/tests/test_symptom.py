"""Symptom extraction and question-engine tests."""
from app.schemas.common import Symptom
from app.services.symptom_service import QuestionEngine, SymptomService

svc = SymptomService()
qe = QuestionEngine()


def test_extract_basic_symptoms():
    symptoms = svc.extract("I've had a headache since yesterday and I feel slightly dizzy")
    names = {s.name for s in symptoms}
    assert "headache" in names
    assert "dizziness" in names


def test_extract_severity_and_duration():
    symptoms = svc.extract("My headache is 6/10 and I've had it for 2 days")
    headache = next(s for s in symptoms if s.name == "headache")
    assert headache.severity == 6
    assert "2 day" in (headache.duration or "")


def test_extract_onset():
    symptoms = svc.extract("The pain started suddenly")
    # No named symptom here, but onset detection shouldn't crash and returns []
    assert isinstance(symptoms, list)


def test_merge_updates_existing():
    existing = [Symptom(name="headache")]
    new = [Symptom(name="headache", severity=7)]
    merged = svc.merge(existing, new)
    assert len(merged) == 1
    assert merged[0].severity == 7


def test_question_engine_avoids_repeats():
    symptoms = [Symptom(name="headache")]
    first = qe.next_question(symptoms, [])
    second = qe.next_question(symptoms, [first])
    assert first != second


def test_question_engine_skips_already_known_attribute():
    # Onset and severity already known -> the question fishing for both should
    # be skipped entirely, not just avoided-if-already-asked.
    symptoms = [Symptom(name="headache", onset="gradual", severity=2)]
    q = qe.next_question(symptoms, [])
    assert "suddenly or gradually" not in q
    assert "how severe" not in q.lower()


def test_question_engine_skips_already_mentioned_related_symptom():
    # "vomiting" was already extracted as its own symptom, so the headache
    # question asking "do you have ... vomiting ..." should be skipped.
    symptoms = [
        Symptom(name="headache", onset="gradual", severity=2),
        Symptom(name="vomiting"),
    ]
    q = qe.next_question(symptoms, [])
    assert "fever, vomiting" not in q
