"""Deterministic safety / red-flag detection engine (PRD sections 18, 31, 49).

This engine runs ALONGSIDE — and independently of — the LLM. Its verdict can
override the LLM's conversational output. It never lowers a risk level that a
rule has raised.
"""
import re
from dataclasses import dataclass, field

from app.safety.rules import (
    ALL_RULES,
    EMERGENCY_RULES,
    SPECIAL_FLAGS,
    URGENT_RULES,
    Rule,
)
from app.schemas.common import RiskLevel


@dataclass
class SafetyVerdict:
    risk_level: RiskLevel = RiskLevel.UNKNOWN
    red_flags: list[str] = field(default_factory=list)
    matched_rule_ids: list[str] = field(default_factory=list)
    special_flags: list[str] = field(default_factory=list)
    is_emergency: bool = False

    def merge(self, other: "SafetyVerdict") -> "SafetyVerdict":
        """Combine two verdicts, keeping the highest risk (monotonic escalation)."""
        merged = SafetyVerdict()
        merged.risk_level = (
            self.risk_level
            if self.risk_level.rank >= other.risk_level.rank
            else other.risk_level
        )
        merged.red_flags = _dedupe(self.red_flags + other.red_flags)
        merged.matched_rule_ids = _dedupe(
            self.matched_rule_ids + other.matched_rule_ids
        )
        merged.special_flags = _dedupe(self.special_flags + other.special_flags)
        merged.is_emergency = merged.risk_level == RiskLevel.EMERGENCY
        return merged


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def _phrase_present(phrase: str, text: str) -> bool:
    return phrase.lower() in text


def _rule_matches(rule: Rule, text: str) -> bool:
    if rule.mode == "any":
        return any(_phrase_present(p, text) for p in rule.patterns)
    # mode == "all": each entry in patterns is a synonym-group
    for group in rule.patterns:
        if not any(_phrase_present(p, text) for p in group):
            return False
    return True


class SafetyService:
    """Rule-based triage classifier."""

    def evaluate_text(self, text: str) -> SafetyVerdict:
        normalized = _normalize(text)
        verdict = SafetyVerdict()

        for rule in ALL_RULES:
            if _rule_matches(rule, normalized):
                verdict.matched_rule_ids.append(rule.id)
                if rule.red_flag_label:
                    verdict.red_flags.append(rule.red_flag_label)
                if rule.risk_level.rank > verdict.risk_level.rank:
                    verdict.risk_level = rule.risk_level

        for flag, phrases in SPECIAL_FLAGS.items():
            if any(_phrase_present(p, normalized) for p in phrases):
                verdict.special_flags.append(flag)

        verdict.red_flags = _dedupe(verdict.red_flags)
        verdict.is_emergency = verdict.risk_level == RiskLevel.EMERGENCY
        return verdict

    def evaluate_conversation(self, messages: list[str]) -> SafetyVerdict:
        """Evaluate the full user side of a conversation.

        Red flags are cumulative across turns: a symptom mentioned earlier still
        counts even if a later message doesn't repeat it. Crucially, multi-symptom
        ("all"-mode) rules must also fire when their triggers are spread across
        separate turns (e.g. "chest pain" in one message, "shortness of breath" in
        the next), so the concatenation of all user messages is evaluated too.
        """
        verdict = SafetyVerdict()
        for msg in messages:
            verdict = verdict.merge(self.evaluate_text(msg))
        # Combined pass catches cross-turn co-occurrence (PRD section 9).
        combined = " ".join(messages)
        verdict = verdict.merge(self.evaluate_text(combined))
        return verdict

    def has_self_harm(self, verdict: SafetyVerdict) -> bool:
        return "suicidal_ideation" in verdict.matched_rule_ids
