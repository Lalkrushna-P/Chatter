"""Symptom extraction and the conversational question engine (PRD FR-02, section 9).

Extraction is rule-based (regex + keyword) so it works without an LLM. When an
LLM is configured it could be swapped in, but a deterministic extractor is easier
to audit for a health application (PRD section 45).
"""
import re
from dataclasses import dataclass
from typing import Optional

from app.schemas.common import Symptom

# Common symptom vocabulary -> canonical name
SYMPTOM_LEXICON = {
    "headache": ["headache", "head ache", "head pain", "migraine"],
    "dizziness": ["dizzy", "dizziness", "lightheaded", "light headed", "vertigo"],
    "fever": ["fever", "temperature", "feverish", "hot and cold"],
    "cough": ["cough", "coughing"],
    "sore throat": ["sore throat", "throat pain", "scratchy throat"],
    "chest pain": ["chest pain", "chest pressure", "chest tightness"],
    "shortness of breath": ["shortness of breath", "short of breath",
                             "difficulty breathing", "trouble breathing",
                             "can't breathe", "cant breathe"],
    "abdominal pain": ["abdominal pain", "stomach pain", "stomach ache",
                       "belly pain", "tummy pain", "stomach hurt", "belly hurt",
                       "tummy hurt", "stomach cramp", "abdomen"],
    "nausea": ["nausea", "nauseous", "feel sick"],
    "vomiting": ["vomiting", "throwing up", "throw up", "vomited"],
    "back pain": ["back pain", "backache"],
    "fatigue": ["fatigue", "tired", "exhausted", "no energy"],
    "rash": ["rash", "skin rash", "hives"],
    "diarrhea": ["diarrhea", "diarrhoea", "loose stool"],
    "cold": ["cold", "runny nose", "stuffy nose", "congestion"],
    "numbness": ["numbness", "numb", "tingling"],
    "weakness": ["weakness", "weak"],
    "joint pain": ["joint pain", "joint ache", "achy joints", "sore joints",
                   "joint hurts", "joints hurt"],
    "ear pain": ["ear pain", "earache", "ear ache", "ear hurts"],
    "eye pain": ["eye pain", "eye redness", "red eye", "eyes are red", "itchy eyes"],
    "insomnia": ["can't sleep", "cant sleep", "trouble sleeping", "insomnia",
                 "not sleeping"],
    "palpitations": ["palpitations", "heart racing", "heart is racing",
                     "racing heart", "heart pounding", "irregular heartbeat"],
    "swelling": ["swelling", "swollen legs", "swollen ankles", "leg swelling",
                 "ankle swelling", "edema"],
    "constipation": ["constipation", "constipated", "can't poop", "cant poop",
                     "haven't pooped", "havent pooped"],
}

ONSET_PATTERNS = {
    "sudden": ["sudden", "suddenly", "out of nowhere", "all at once", "came on fast"],
    "gradual": ["gradual", "gradually", "slowly", "over time", "creeping"],
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'"))


class SymptomService:
    def extract(self, text: str) -> list[Symptom]:
        norm = _normalize(text)
        found: dict[str, Symptom] = {}

        for canonical, variants in SYMPTOM_LEXICON.items():
            if any(v in norm for v in variants):
                found[canonical] = Symptom(name=canonical)

        # Enrich each found symptom with shared attributes from the sentence.
        severity = self._extract_severity(norm)
        duration = self._extract_duration(norm)
        onset = self._extract_onset(norm)

        for symptom in found.values():
            if severity is not None:
                symptom.severity = severity
            if duration:
                symptom.duration = duration
            if onset:
                symptom.onset = onset
        return list(found.values())

    def merge(self, existing: list[Symptom], new: list[Symptom]) -> list[Symptom]:
        """Merge newly extracted symptoms into the running state without duplicates."""
        by_name = {s.name: s for s in existing}
        for s in new:
            if s.name in by_name:
                cur = by_name[s.name]
                cur.severity = s.severity if s.severity is not None else cur.severity
                cur.duration = s.duration or cur.duration
                cur.onset = s.onset or cur.onset
                cur.location = s.location or cur.location
            else:
                by_name[s.name] = s
        return list(by_name.values())

    def _extract_severity(self, text: str) -> Optional[int]:
        m = re.search(r"\b(\d{1,2})\s*(?:/|out of)\s*10\b", text)
        if m:
            val = int(m.group(1))
            return min(val, 10)
        if any(w in text for w in ["excruciating", "unbearable", "worst"]):
            return 10
        if "severe" in text:
            return 8
        if "moderate" in text:
            return 5
        if "mild" in text or "slight" in text:
            return 2
        return None

    def _extract_duration(self, text: str) -> Optional[str]:
        m = re.search(
            r"\b(?:for|since|about|around)?\s*(\d+)\s*(minute|min|hour|hr|day|week|month|year)s?\b",
            text,
        )
        if m:
            return f"{m.group(1)} {m.group(2)}{'s' if int(m.group(1)) != 1 else ''}"
        for phrase in ["yesterday", "this morning", "last night", "today",
                       "a few days", "several days", "couple of days"]:
            if phrase in text:
                return phrase
        return None

    def _extract_onset(self, text: str) -> Optional[str]:
        for onset, variants in ONSET_PATTERNS.items():
            if any(v in text for v in variants):
                return onset
        return None


# ---------------------------------------------------------------------------
# Follow-up question engine (PRD section 9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FollowUpQuestion:
    """A candidate follow-up question, tagged with what it's trying to learn.

    `skip_if_attrs`: Symptom attributes (severity/duration/onset/...) this
    question is fishing for — skipped once ALL of them are already known
    (from the initial message or an earlier answer), so the same ground
    isn't re-asked once it's been volunteered.
    `skip_if_any_present`: canonical symptom names (e.g. "fever", "nausea")
    this question is really asking "do you also have X" — skipped if the
    user already separately mentioned any of them, since re-asking "do you
    have fever?" after they already said they have a fever is redundant.
    """

    text: str
    skip_if_attrs: tuple[str, ...] = ()
    skip_if_any_present: tuple[str, ...] = ()


# Symptom-specific question banks. Ordered by clinical usefulness.
QUESTION_BANK: dict[str, list[FollowUpQuestion]] = {
    "headache": [
        FollowUpQuestion(
            "Where exactly is the headache located, and did it start suddenly or gradually?",
            skip_if_attrs=("onset",),
        ),
        FollowUpQuestion(
            "On a scale of 0-10, how severe is the pain?", skip_if_attrs=("severity",)
        ),
        FollowUpQuestion(
            "Do you have any fever, vomiting, vision problems, or weakness/numbness?",
            skip_if_any_present=("fever", "vomiting", "numbness", "weakness"),
        ),
        FollowUpQuestion("Have you had any recent head injury?"),
    ],
    "chest pain": [
        FollowUpQuestion(
            "When did the chest pain start, and is it happening right now?",
            skip_if_attrs=("onset",),
        ),
        FollowUpQuestion(
            "Is it a pressure, squeezing, burning, or stabbing sensation, and does it "
            "spread to your arm, jaw, or back?"
        ),
        FollowUpQuestion(
            "Are you experiencing shortness of breath, sweating, or nausea?",
            skip_if_any_present=("shortness of breath", "nausea"),
        ),
    ],
    "sore throat": [
        FollowUpQuestion(
            "Do you also have a fever, cough, difficulty swallowing, or difficulty breathing?",
            skip_if_any_present=("fever", "cough", "shortness of breath"),
        ),
        FollowUpQuestion(
            "How many days have you had the sore throat?", skip_if_attrs=("duration",)
        ),
    ],
    "fever": [
        FollowUpQuestion(
            "How high is your temperature, and how many days have you had it?",
            skip_if_attrs=("duration",),
        ),
        FollowUpQuestion(
            "Do you have any other symptoms such as a rash, stiff neck, difficulty "
            "breathing, or confusion?",
            skip_if_any_present=("rash", "shortness of breath"),
        ),
    ],
    "cough": [
        FollowUpQuestion(
            "How long have you had the cough, and are you bringing up any phlegm or blood?",
            skip_if_attrs=("duration",),
        ),
        FollowUpQuestion(
            "Do you have a fever, shortness of breath, or chest pain?",
            skip_if_any_present=("fever", "shortness of breath", "chest pain"),
        ),
    ],
    "abdominal pain": [
        FollowUpQuestion(
            "Where in your abdomen is the pain, and how severe is it from 0-10?",
            skip_if_attrs=("severity",),
        ),
        FollowUpQuestion(
            "Do you have vomiting, fever, or blood in your stool?",
            skip_if_any_present=("vomiting", "fever"),
        ),
    ],
    "dizziness": [
        FollowUpQuestion(
            "Did the dizziness start suddenly, and do you have any weakness, numbness, "
            "or trouble speaking?",
            skip_if_attrs=("onset",),
        ),
        FollowUpQuestion("Do you feel faint, or is the room spinning?"),
    ],
    "back pain": [
        FollowUpQuestion(
            "Did the back pain follow an injury, and do you have any numbness, "
            "tingling, or trouble controlling your bladder or bowels?",
            skip_if_any_present=("numbness",),
        ),
    ],
    "rash": [
        FollowUpQuestion(
            "Is the rash spreading, and do you have a fever or any swelling of the "
            "lips, tongue, or face?",
            skip_if_any_present=("fever", "swelling"),
        ),
    ],
    "joint pain": [
        FollowUpQuestion(
            "Which joint(s) are affected, and is there any redness, warmth, or swelling?",
            skip_if_any_present=("swelling",),
        ),
        FollowUpQuestion(
            "Did this follow an injury, and does it affect your ability to move the joint?"
        ),
    ],
    "ear pain": [
        FollowUpQuestion(
            "Is it in one ear or both, and do you have any fever, hearing loss, or "
            "discharge from the ear?",
            skip_if_any_present=("fever",),
        ),
    ],
    "eye pain": [
        FollowUpQuestion(
            "Is there any vision change, light sensitivity, or discharge from the eye?"
        ),
    ],
    "insomnia": [
        FollowUpQuestion(
            "How many nights has this been going on, and is anything specific keeping "
            "you awake (pain, stress, racing thoughts)?",
            skip_if_attrs=("duration",),
        ),
    ],
    "palpitations": [
        FollowUpQuestion(
            "Does it happen at rest or with activity, and do you have any chest pain, "
            "shortness of breath, or dizziness with it?",
            skip_if_any_present=("chest pain", "shortness of breath", "dizziness"),
        ),
    ],
    "swelling": [
        FollowUpQuestion(
            "Is the swelling in one leg or both, and do you have any shortness of "
            "breath, chest pain, or pain in the calf?",
            skip_if_any_present=("shortness of breath", "chest pain"),
        ),
    ],
    "constipation": [
        FollowUpQuestion(
            "How many days has it been, and do you have any severe abdominal pain, "
            "vomiting, or blood in your stool?",
            skip_if_attrs=("duration",),
            skip_if_any_present=("vomiting", "abdominal pain"),
        ),
    ],
}

GENERIC_QUESTIONS = [
    FollowUpQuestion(
        "How long have you been experiencing this, and how severe would you say it "
        "is from 0-10?",
        skip_if_attrs=("duration", "severity"),
    ),
    FollowUpQuestion("Have you noticed any other symptoms alongside this?"),
    FollowUpQuestion("Have your symptoms been getting better, worse, or staying the same?"),
]

# Baseline context questions (PRD section 33)
CONTEXT_QUESTIONS = {
    "subject": "Before we continue — is this assessment for you or for someone else?",
    "age": "What is the person's age? Some guidance differs for children and older adults.",
    "pregnancy": "Are you currently pregnant or could you be pregnant?",
}

_SOMEONE_ELSE_PHRASES = [
    "someone else", "another person", "my friend", "my wife", "my husband",
    "my partner", "my mother", "my father", "my parent", "my sister",
    "my brother", "my son", "my daughter", "my child", "my kid", "my baby",
    "not for me", "not me",
]
_PREGNANT_YES_PHRASES = ["yes", "pregnant", "i am", "i'm", "could be"]
_PREGNANT_NO_PHRASES = ["no", "not pregnant", "n/a", "na"]


def parse_context_answer(awaiting: str, text: str):
    """Deterministically interpret a free-text reply to a pending context
    question (PRD section 33). Rule-based, like the rest of this module, so a
    single-word or short reply is enough to move the conversation forward
    instead of re-asking the same structured question indefinitely.
    """
    normalized = _normalize(text)
    if awaiting == "subject":
        if any(p in normalized for p in _SOMEONE_ELSE_PHRASES):
            return "someone_else"
        return "self"

    if awaiting == "age":
        m = re.search(r"\b(\d{1,3})\b", normalized)
        return int(m.group(1)) if m else None

    if awaiting == "pregnancy":
        if any(p in normalized for p in _PREGNANT_NO_PHRASES):
            return False
        if any(p in normalized for p in _PREGNANT_YES_PHRASES):
            return True
        return False

    return None


class QuestionEngine:
    def next_question(
        self,
        symptoms: list[Symptom],
        questions_asked: list[str],
    ) -> Optional[str]:
        """Pick the next best unanswered question, avoiding repeats (PRD section 19)
        and skipping anything the user has already told us — whether asked
        directly (an attribute like severity/onset already extracted) or
        volunteered unprompted (a related symptom already mentioned).
        """
        asked = set(questions_asked)
        known_names = {s.name for s in symptoms}

        # Prefer questions tied to the most severe / first symptom.
        ordered = sorted(symptoms, key=lambda s: (s.severity or 0), reverse=True)
        for symptom in ordered:
            for q in QUESTION_BANK.get(symptom.name, []):
                if q.text in asked or self._is_redundant(q, symptom, known_names):
                    continue
                return q.text

        fallback_symptom = ordered[0] if ordered else None
        for q in GENERIC_QUESTIONS:
            if q.text in asked or self._is_redundant(q, fallback_symptom, known_names):
                continue
            return q.text
        return None

    @staticmethod
    def _is_redundant(
        q: FollowUpQuestion, symptom: Optional[Symptom], known_names: set[str]
    ) -> bool:
        if q.skip_if_attrs and symptom is not None:
            if all(getattr(symptom, attr, None) for attr in q.skip_if_attrs):
                return True
        if q.skip_if_any_present and known_names & set(q.skip_if_any_present):
            return True
        return False
