"""Deterministic lab-value reference ranges and flagging.

CLINICAL SAFETY NOTE
--------------------
Like `safety/rules.py`, this is an ENGINEERING SCAFFOLD, not a clinically
validated reference-range table. Ranges vary by lab, age, sex, and units;
these are common adult defaults for demo/screening purposes only and must be
reviewed by qualified clinicians before real-world use.

Matching common lab report text mirrors `symptom_service.py`'s approach:
plain regex over normalized text, so flagging never depends on the LLM.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LabRange:
    canonical_name: str
    aliases: list[str]
    unit: str
    low: float
    high: float


# Common adult reference ranges (illustrative defaults only).
LAB_RANGES: list[LabRange] = [
    LabRange("hemoglobin", ["hemoglobin", "haemoglobin", "hgb", "hb"], "g/dL", 12.0, 17.5),
    LabRange("wbc", ["wbc", "white blood cell count", "white blood cells", "leukocytes"],
              "10^3/uL", 4.0, 11.0),
    LabRange("platelets", ["platelets", "platelet count", "plt"], "10^3/uL", 150.0, 450.0),
    LabRange("fasting glucose", ["fasting glucose", "glucose fasting", "fbs"],
              "mg/dL", 70.0, 99.0),
    LabRange("total cholesterol", ["total cholesterol", "cholesterol total", "cholesterol"],
              "mg/dL", 0.0, 200.0),
    LabRange("ldl", ["ldl", "ldl cholesterol", "ldl-c"], "mg/dL", 0.0, 100.0),
    LabRange("hdl", ["hdl", "hdl cholesterol", "hdl-c"], "mg/dL", 40.0, 200.0),
    LabRange("creatinine", ["creatinine"], "mg/dL", 0.6, 1.3),
    LabRange("alt", ["alt", "sgpt", "alanine aminotransferase"], "U/L", 7.0, 56.0),
    LabRange("ast", ["ast", "sgot", "aspartate aminotransferase"], "U/L", 8.0, 48.0),
    LabRange("tsh", ["tsh", "thyroid stimulating hormone"], "mIU/L", 0.4, 4.0),
    LabRange("sodium", ["sodium", "serum sodium", "na+", "na"], "mEq/L", 135.0, 145.0),
    LabRange("potassium", ["potassium", "serum potassium", "k+", "k"], "mEq/L", 3.5, 5.0),
    LabRange("hba1c", ["hba1c", "hemoglobin a1c", "glycated hemoglobin", "a1c"], "%", 4.0, 5.6),
    LabRange("vitamin d", ["vitamin d", "25-hydroxyvitamin d", "25-oh vitamin d", "vit d"],
              "ng/mL", 30.0, 100.0),
    LabRange("vitamin b12", ["vitamin b12", "cobalamin", "b12"], "pg/mL", 200.0, 900.0),
]

_ALIAS_TO_RANGE: dict[str, LabRange] = {
    alias: r for r in LAB_RANGES for alias in r.aliases
}

# Longest aliases first so "fasting glucose" matches before "glucose fasting" quirks etc.
_ALIASES_SORTED = sorted(_ALIAS_TO_RANGE.keys(), key=len, reverse=True)

_ALIAS_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(a) for a in _ALIASES_SORTED) + r")\b"
    r"[^\d\-]{0,20}?(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


@dataclass
class LabValue:
    name: str
    value: float
    unit: str
    reference_low: float
    reference_high: float
    flag: str  # "low" | "normal" | "high"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def extract_lab_values(text: str) -> list[LabValue]:
    """Pull recognizable 'test name ... value' pairs from free text and flag them
    against reference ranges. Deterministic — no LLM involved (PRD-style safety
    principle: clinical flags must not depend solely on the model).
    """
    normalized = _normalize(text)
    found: dict[str, LabValue] = {}

    for match in _ALIAS_PATTERN.finditer(normalized):
        alias = match.group(1)
        raw_value = match.group(2)
        lab_range = _ALIAS_TO_RANGE.get(alias)
        if lab_range is None:
            continue
        try:
            value = float(raw_value)
        except ValueError:
            continue

        if value < lab_range.low:
            flag = "low"
        elif value > lab_range.high:
            flag = "high"
        else:
            flag = "normal"

        # First match wins per canonical test (avoid duplicate/near-duplicate hits).
        found.setdefault(
            lab_range.canonical_name,
            LabValue(
                name=lab_range.canonical_name,
                value=value,
                unit=lab_range.unit,
                reference_low=lab_range.low,
                reference_high=lab_range.high,
                flag=flag,
            ),
        )

    return list(found.values())


def worst_flag(values: list[LabValue]) -> Optional[str]:
    """Return the most clinically notable flag present, or None if all normal."""
    if any(v.flag != "normal" for v in values):
        # Treat "high"/"low" as equally notable for this coarse scaffold.
        return next(v.flag for v in values if v.flag != "normal")
    return None
