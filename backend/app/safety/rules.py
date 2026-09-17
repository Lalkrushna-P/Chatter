"""Deterministic red-flag rule definitions.

CLINICAL SAFETY NOTE
--------------------
This ruleset is an ENGINEERING SCAFFOLD, not a clinically validated triage
protocol. Per PRD sections 18 and 50, the rules must be developed and reviewed
with qualified clinical expertise before any production/real-world use. It is
intentionally biased toward over-triage (false positives) because, per PRD
section 51, a false negative on an emergency symptom is a far more serious
failure than conversational inconvenience.

Matching is keyword/phrase based over normalized text. Each rule is either:
  - "any": fires if any listed phrase is present, or
  - "all": fires only if every listed group is present (each group is a list of
    synonyms; a group is satisfied if any of its synonyms match).
"""
from dataclasses import dataclass, field
from typing import Literal

from app.schemas.common import RiskLevel


@dataclass(frozen=True)
class Rule:
    id: str
    description: str
    risk_level: RiskLevel
    mode: Literal["any", "all"]
    # For mode="any": flat list of phrases.
    # For mode="all": list of synonym-groups; every group must match.
    patterns: list = field(default_factory=list)
    red_flag_label: str = ""


# ---------------------------------------------------------------------------
# LEVEL 1 — EMERGENCY (PRD section 7, 18)
# ---------------------------------------------------------------------------
EMERGENCY_RULES: list[Rule] = [
    Rule(
        id="cardiac_chest_pain",
        description="Chest pain with cardiac red-flag features",
        risk_level=RiskLevel.EMERGENCY,
        mode="all",
        patterns=[
            ["chest pain", "chest pressure", "chest tightness", "pain in my chest",
             "chest is tight", "squeezing chest"],
            ["shortness of breath", "short of breath", "can't breathe",
             "cant breathe", "difficulty breathing", "trouble breathing",
             "hard to breathe", "sweating", "cold sweat", "clammy", "faint",
             "fainting", "passed out", "nausea", "nauseous", "pain in my arm",
             "arm pain", "jaw pain", "radiating"],
        ],
        red_flag_label="Chest pain with breathing difficulty, sweating, or radiating pain",
    ),
    Rule(
        id="stroke_signs",
        description="Signs of stroke (FAST)",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "face drooping", "drooping face", "one side of my face",
            "weakness on one side", "numbness on one side", "one sided weakness",
            "can't move my arm", "cant move my arm", "slurred speech",
            "can't speak", "cant speak", "difficulty speaking", "trouble speaking",
            "sudden confusion", "face is drooping", "arm weakness",
        ],
        red_flag_label="Possible stroke signs (facial droop, one-sided weakness, speech difficulty)",
    ),
    Rule(
        id="thunderclap_headache",
        description="Sudden severe headache",
        risk_level=RiskLevel.EMERGENCY,
        mode="all",
        patterns=[
            ["headache", "head pain"],
            ["sudden", "worst headache", "thunderclap", "explosive",
             "came on suddenly", "out of nowhere", "worst ever"],
        ],
        red_flag_label="Sudden 'worst-ever' headache",
    ),
    Rule(
        id="severe_breathing",
        description="Severe difficulty breathing",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "can't breathe", "cant breathe", "cannot breathe",
            "struggling to breathe", "gasping", "choking", "turning blue",
            "lips are blue", "severe difficulty breathing",
        ],
        red_flag_label="Severe difficulty breathing",
    ),
    Rule(
        id="loss_of_consciousness",
        description="Loss of consciousness / unresponsive",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "passed out", "lost consciousness", "unconscious", "unresponsive",
            "blacked out", "collapsed", "won't wake up", "wont wake up",
            "not waking up",
        ],
        red_flag_label="Loss of consciousness",
    ),
    Rule(
        id="seizure",
        description="Active or recent seizure",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=["seizure", "convulsion", "convulsing", "fitting", "having a fit"],
        red_flag_label="Seizure",
    ),
    Rule(
        id="anaphylaxis",
        description="Severe allergic reaction",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "anaphylaxis", "anaphylactic", "throat closing", "throat is closing",
            "tongue swelling", "swollen tongue", "can't swallow and breathe",
            "face swelling up", "severe allergic reaction", "hives all over",
        ],
        red_flag_label="Severe allergic reaction (throat/tongue swelling, difficulty breathing)",
    ),
    Rule(
        id="severe_bleeding",
        description="Severe uncontrolled bleeding",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "won't stop bleeding", "wont stop bleeding", "uncontrolled bleeding",
            "bleeding heavily", "gushing blood", "lost a lot of blood",
            "severe bleeding", "hemorrhage", "coughing up a lot of blood",
            "vomiting blood",
        ],
        red_flag_label="Severe / uncontrolled bleeding",
    ),
    Rule(
        id="suicidal_ideation",
        description="Self-harm / suicidal ideation (routes to crisis support)",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "kill myself", "suicidal", "suicide", "end my life", "want to die",
            "hurt myself", "harm myself", "self harm", "self-harm",
            "don't want to live", "dont want to live", "no reason to live",
            "take my own life",
        ],
        red_flag_label="Self-harm / suicidal thoughts",
    ),
    Rule(
        id="overdose",
        description="Medication overdose / poisoning",
        risk_level=RiskLevel.EMERGENCY,
        mode="any",
        patterns=[
            "overdose", "overdosed", "took too many pills", "too many tablets",
            "poisoned", "swallowed poison", "ingested chemicals",
        ],
        red_flag_label="Possible overdose / poisoning",
    ),
    Rule(
        id="anaphylaxis_infant_fever",
        description="Infant with fever (very low age handled separately too)",
        risk_level=RiskLevel.EMERGENCY,
        mode="all",
        patterns=[
            ["stiff neck", "neck stiffness"],
            ["fever", "high temperature", "rash that doesn't fade",
             "rash that doesnt fade", "sensitive to light", "photophobia"],
        ],
        red_flag_label="Fever with stiff neck / non-blanching rash (possible meningitis)",
    ),
]

# ---------------------------------------------------------------------------
# LEVEL 2 — URGENT (PRD section 7)
# ---------------------------------------------------------------------------
URGENT_RULES: list[Rule] = [
    Rule(
        id="high_persistent_fever",
        description="Persistent high fever",
        risk_level=RiskLevel.URGENT,
        mode="all",
        patterns=[
            ["fever", "high temperature", "temperature of", "103", "104", "40 degrees"],
            ["days", "not going down", "won't go down", "wont go down",
             "persistent", "getting worse", "worsening", "several days"],
        ],
        red_flag_label="Persistent / high fever",
    ),
    Rule(
        id="dehydration",
        description="Significant dehydration",
        risk_level=RiskLevel.URGENT,
        mode="any",
        patterns=[
            "severe dehydration", "can't keep fluids down", "cant keep fluids down",
            "not urinating", "haven't peed", "havent peed", "very dizzy standing",
            "no tears", "sunken eyes",
        ],
        red_flag_label="Signs of significant dehydration",
    ),
    Rule(
        id="persistent_vomiting",
        description="Persistent vomiting",
        risk_level=RiskLevel.URGENT,
        mode="any",
        patterns=[
            "can't stop vomiting", "cant stop vomiting", "vomiting for",
            "keep throwing up", "persistent vomiting", "vomiting everything",
        ],
        red_flag_label="Persistent vomiting",
    ),
    Rule(
        id="worsening_abdominal_pain",
        description="Severe / worsening abdominal pain",
        risk_level=RiskLevel.URGENT,
        mode="all",
        patterns=[
            ["abdominal pain", "stomach pain", "belly pain", "tummy pain",
             "pain in my abdomen", "stomach ache"],
            ["severe", "worsening", "getting worse", "unbearable", "sharp",
             "can't stand", "8/10", "9/10", "10/10"],
        ],
        red_flag_label="Severe or worsening abdominal pain",
    ),
    Rule(
        id="breathing_difficulty",
        description="New/standalone difficulty breathing (severe variants are emergency)",
        risk_level=RiskLevel.URGENT,
        mode="any",
        patterns=[
            "difficulty breathing", "trouble breathing", "short of breath",
            "shortness of breath", "hard to breathe", "breathless",
            "wheezing", "can't catch my breath", "cant catch my breath",
        ],
        red_flag_label="Difficulty breathing",
    ),
    Rule(
        id="new_neuro_symptoms",
        description="New neurological symptoms without clear emergency criteria",
        risk_level=RiskLevel.URGENT,
        mode="any",
        patterns=[
            "vision problems", "blurred vision", "double vision", "numbness",
            "tingling", "pins and needles", "weakness in my", "hard to focus",
        ],
        red_flag_label="New neurological symptoms",
    ),
]

# ---------------------------------------------------------------------------
# Special-population / special-flow flags (PRD sections 31, 33)
# These do not by themselves set a level but tighten thresholds and route flows.
# ---------------------------------------------------------------------------
SPECIAL_FLAGS = {
    "pregnancy": [
        "pregnant", "pregnancy", "expecting", "weeks pregnant", "trimester",
    ],
    "infant": [
        "my baby", "newborn", "infant", "months old", "my toddler",
    ],
    "child": [
        "my child", "my son", "my daughter", "my kid", "years old",
    ],
}

ALL_RULES = EMERGENCY_RULES + URGENT_RULES
