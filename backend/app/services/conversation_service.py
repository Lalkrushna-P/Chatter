"""Conversation manager — orchestrates the full MVP pipeline (PRD sections 49, 52).

    User -> Conversation -> Symptom Extraction -> Safety/Red-Flag Detection
         -> Risk Assessment -> RAG Retrieval -> Evidence -> LLM Response
         -> Output Safety Validation -> User

Medical safety decisions never depend solely on the LLM: the deterministic safety
engine's verdict is applied both before and after generation.
"""
from typing import Optional

from app.config import Settings, get_settings
from app.prompts.system_prompts import SYSTEM_PROMPT, build_user_prompt
from app.repositories.store import InMemoryStore, get_store
from app.schemas.chat import AssessmentSummary, ChatRequest, ChatResponse
from app.schemas.common import RiskLevel, Symptom
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.response_builder import (
    DISCLAIMER,
    OutputSafetyValidator,
    recommended_action,
    warning_signs_for,
)
from app.services.safety_service import SafetyService, SafetyVerdict
from app.services.symptom_service import (
    CONTEXT_QUESTIONS,
    QuestionEngine,
    SymptomService,
)


class ConversationManager:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.store: InMemoryStore = get_store()
        self.safety = SafetyService()
        self.symptoms = SymptomService()
        self.questions = QuestionEngine()
        self.rag = RAGService(self.settings, self.store)
        self.llm = LLMService(self.settings)
        self.validator = OutputSafetyValidator(self.settings)

    async def handle_message(self, req: ChatRequest) -> ChatResponse:
        # 1. Conversation
        conv = (
            self.store.get_conversation(req.conversation_id)
            if req.conversation_id
            else None
        )
        if conv is None:
            conv = self.store.create_conversation(user_id=None)
        conversation_id = conv["id"]

        self.store.add_message(conversation_id, "user", req.message)

        # 2. Load running assessment state
        state = self._load_state(conversation_id)

        # Record patient context if provided this turn
        if req.subject:
            state["subject"] = req.subject
        if req.age is not None:
            state["age"] = req.age
        if req.is_pregnant is not None:
            state["is_pregnant"] = req.is_pregnant

        # 3. Symptom extraction (merge into state)
        existing = [Symptom(**s) for s in state.get("symptoms", [])]
        new = self.symptoms.extract(req.message)
        merged = self.symptoms.merge(existing, new)
        state["symptoms"] = [s.model_dump() for s in merged]

        # 4. Safety engine over the FULL user-side conversation (cumulative)
        user_messages = [
            m["content"]
            for m in self.store.get_messages(conversation_id)
            if m["role"] == "user"
        ]
        verdict = self.safety.evaluate_conversation(user_messages)

        # Tighten thresholds for special populations (PRD sections 31, 33)
        verdict = self._apply_special_population_rules(verdict, state)

        # Baseline floor: once at least one symptom is identified and no red flag
        # fired, resolve to Level 4 self-care/monitoring instead of staying
        # 'unknown' indefinitely (PRD section 7, Level 4).
        if verdict.risk_level == RiskLevel.UNKNOWN and merged:
            verdict.risk_level = RiskLevel.SELF_CARE

        # 5. Self-harm short-circuit
        if self.safety.has_self_harm(verdict):
            return self._finalize(
                conversation_id,
                state,
                message=self.validator.self_harm_message(),
                verdict=verdict,
                possible=[],
                sources=[],
                follow_up=None,
            )

        # 6. Emergency short-circuit — do not continue lengthy questioning
        if verdict.risk_level == RiskLevel.EMERGENCY:
            return self._finalize(
                conversation_id,
                state,
                message=self.validator.emergency_message(),
                verdict=verdict,
                possible=[],
                sources=[],
                follow_up=None,
            )

        # 7. Ask baseline context questions early if missing
        context_q = self._pending_context_question(state, verdict)

        # 8. RAG retrieval
        query = self.rag.build_query(req.message, merged)
        evidence = await self.rag.retrieve(query)
        sources = self.rag.to_sources(evidence)
        possible = self._possible_explanations(evidence)

        # 9. LLM generation grounded in evidence
        history = self.store.get_messages(conversation_id)
        user_prompt = build_user_prompt(
            user_message=req.message,
            history=history,
            symptoms=merged,
            risk_level=verdict.risk_level,
            red_flags=verdict.red_flags,
            evidence=evidence,
            special_flags=verdict.special_flags,
        )
        llm_text = await self.llm.generate(SYSTEM_PROMPT, user_prompt)

        # 10. Output safety validation
        safe_text = self.validator.sanitize(llm_text)

        # 11. Follow-up question (context question takes priority)
        follow_up = context_q or self.questions.next_question(
            merged, state.get("questions_asked", [])
        )
        if follow_up:
            state.setdefault("questions_asked", []).append(follow_up)

        return self._finalize(
            conversation_id,
            state,
            message=safe_text,
            verdict=verdict,
            possible=possible,
            sources=sources,
            follow_up=follow_up,
        )

    # ------------------------------------------------------------------
    def _finalize(
        self,
        conversation_id: str,
        state: dict,
        *,
        message: str,
        verdict: SafetyVerdict,
        possible: list[str],
        sources: list,
        follow_up: Optional[str],
    ) -> ChatResponse:
        state["risk_level"] = verdict.risk_level.value
        state["red_flags"] = verdict.red_flags
        state["possible_explanations"] = possible

        # Compose the message body: LLM text + follow-up question.
        body = message
        if follow_up and verdict.risk_level != RiskLevel.EMERGENCY:
            body = f"{message}\n\n{follow_up}"

        self.store.upsert_assessment(conversation_id, state)
        self.store.update_conversation(
            conversation_id, risk_level=verdict.risk_level.value
        )
        self.store.add_message(conversation_id, "assistant", body)

        return ChatResponse(
            conversation_id=conversation_id,
            message=body,
            risk_level=verdict.risk_level,
            possible_categories=possible,
            red_flags=verdict.red_flags,
            recommended_action=recommended_action(verdict.risk_level),
            follow_up_question=follow_up,
            sources=sources,
            is_emergency=verdict.risk_level == RiskLevel.EMERGENCY,
            disclaimer=DISCLAIMER,
        )

    def _load_state(self, conversation_id: str) -> dict:
        existing = self.store.get_assessment_by_conversation(conversation_id)
        if existing:
            return existing
        return {
            "symptoms": [],
            "questions_asked": [],
            "red_flags": [],
            "risk_level": "unknown",
            "possible_explanations": [],
            "status": "active",
        }

    def _apply_special_population_rules(
        self, verdict: SafetyVerdict, state: dict
    ) -> SafetyVerdict:
        """Raise the floor risk for infants / young children / pregnancy."""
        age = state.get("age")
        is_infant = ("infant" in verdict.special_flags) or (age is not None and age < 1)
        is_pregnant = state.get("is_pregnant") or ("pregnancy" in verdict.special_flags)

        floor = None
        if is_infant:
            floor = RiskLevel.URGENT
        elif is_pregnant and verdict.risk_level.rank >= RiskLevel.ROUTINE.rank:
            floor = RiskLevel.URGENT

        if floor and verdict.risk_level.rank < floor.rank:
            verdict.risk_level = floor
            verdict.is_emergency = floor == RiskLevel.EMERGENCY
        return verdict

    def _pending_context_question(
        self, state: dict, verdict: SafetyVerdict
    ) -> Optional[str]:
        if "subject" not in state:
            return CONTEXT_QUESTIONS["subject"]
        if state.get("subject") == "someone_else" and "age" not in state:
            return CONTEXT_QUESTIONS["age"]
        if "pregnancy" in verdict.special_flags and state.get("is_pregnant") is None:
            return CONTEXT_QUESTIONS["pregnancy"]
        return None

    def _possible_explanations(self, evidence: list) -> list[str]:
        """Derive up to 5 possible categories from retrieved evidence titles.

        Only surfaces possibilities grounded in retrieved documents (PRD section 17).
        """
        seen = []
        for e in evidence:
            title = (e.title or "").strip()
            if title and title not in seen:
                seen.append(title)
        return seen[:5]

    # ------------------------------------------------------------------
    def build_summary(self, conversation_id: str) -> Optional[AssessmentSummary]:
        rec = self.store.get_assessment_by_conversation(conversation_id)
        if not rec:
            return None
        symptoms = [Symptom(**s) for s in rec.get("symptoms", [])]
        risk = RiskLevel(rec.get("risk_level", "unknown"))
        duration = next((s.duration for s in symptoms if s.duration), None)
        severity = next((s.severity for s in symptoms if s.severity is not None), None)
        associated = sorted({a for s in symptoms for a in s.associated_symptoms})

        return AssessmentSummary(
            assessment_id=rec["id"],
            conversation_id=conversation_id,
            symptoms=symptoms,
            duration=duration,
            severity=severity,
            associated_symptoms=associated,
            risk_level=risk,
            possible_explanations=rec.get("possible_explanations", []),
            recommended_action=recommended_action(risk),
            seek_urgent_care_if=warning_signs_for(risk),
            red_flags=rec.get("red_flags", []),
            status=rec.get("status", "active"),
        )
