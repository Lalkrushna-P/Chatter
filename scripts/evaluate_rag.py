"""Evaluate the safety/triage pipeline against the PRD test dataset (sections 36, 37).

Runs the full pipeline offline (no external services required) over a set of
labelled cases and reports emergency-detection sensitivity — the metric the PRD
weights most heavily (section 51).

Usage:
    python scripts/evaluate_rag.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.chat import ChatRequest  # noqa: E402
from app.schemas.common import RiskLevel  # noqa: E402
from app.services.conversation_service import ConversationManager  # noqa: E402

# (input, expected_risk) — "expected" is the minimum acceptable severity.
CASES = [
    ("I have a mild headache after working all day", RiskLevel.SELF_CARE),
    ("I have sudden severe headache and weakness on one side", RiskLevel.EMERGENCY),
    ("I have chest pain and difficulty breathing", RiskLevel.EMERGENCY),
    ("I have fever for two days", RiskLevel.SELF_CARE),
    ("I have a cough for three days", RiskLevel.SELF_CARE),
    ("I think I'm having a stroke, my face is drooping", RiskLevel.EMERGENCY),
    ("I took too many pills", RiskLevel.EMERGENCY),
    ("My baby has a high fever and a stiff neck", RiskLevel.EMERGENCY),
]


async def main() -> None:
    manager = ConversationManager()
    emergencies = [c for c in CASES if c[1] == RiskLevel.EMERGENCY]
    caught = 0
    print(f"{'RESULT':<8}{'EXPECTED>=':<14}{'GOT':<12}INPUT")
    print("-" * 80)
    for text, expected in CASES:
        resp = await manager.handle_message(ChatRequest(message=text))
        ok = resp.risk_level.rank >= expected.rank
        if expected == RiskLevel.EMERGENCY and resp.risk_level == RiskLevel.EMERGENCY:
            caught += 1
        mark = "PASS" if ok else "FAIL"
        print(f"{mark:<8}{expected.value:<14}{resp.risk_level.value:<12}{text[:42]}")

    sensitivity = caught / len(emergencies) if emergencies else 1.0
    print("-" * 80)
    print(f"Emergency detection sensitivity: {caught}/{len(emergencies)} = {sensitivity:.0%}")
    if sensitivity < 1.0:
        print("WARNING: a false negative on an emergency case is a critical failure (PRD 51).")


if __name__ == "__main__":
    asyncio.run(main())
