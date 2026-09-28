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
from app.services.report_service import ReportService
from app.services.response_builder import (
    DISCLAIMER,
    OutputSafetyValidator,
    build_grounded_fallback,
    recommended_action,
    trend_recommended_action,
    warning_signs_for,
)
from app.services.safety_service import SafetyService, SafetyVerdict
from app.services.symptom_service import (
    CONTEXT_QUESTIONS,
    TREND_QUESTION,
    QuestionEngine,
    SymptomService,
    parse_context_answer,
    parse_trend_answer,
)


def _age_descriptor(age: Optional[int]) -> str:
    """A short age-band phrase folded into the RAG query so retrieval — and,
    via the LLM prompt, the generated explanation — actually differs by age
    (e.g. a pediatric vs. an elderly presentation of the same symptom).
    """
    if age is None:
        return ""
    if age < 1:
        return f"age {age} infant"
    if age < 12:
        return f"age {age} child pediatric"
    if age < 18:
        return f"age {age} adolescent teen"
    if age >= 65:
        return f"age {age} elderly older adult"
    return f"age {age} adult"


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
        self.reports = ReportService(self.settings, self.store)

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

        # If a context question (subject/age/pregnancy) was asked last turn,
        # interpret this free-text reply as its answer so the conversation
        # moves on instead of re-asking the same question indefinitely. Keep
        # track of *which* question this was so the reply we generate below
        # actually acknowledges the answer instead of treating "it's for my
        # son" as a fresh, contentless symptom message.
        awaiting_context = state.get("awaiting_context")
        self._consume_context_answer(state, req.message)
        context_ack = self._context_answer_ack(awaiting_context, state)

        # Same idea for "Have your symptoms been getting better, worse, or
        # staying the same?" — the answer directly drives the recommended
        # action below (worse/same/better), independent of the LLM.
        if state.get("awaiting_trend"):
            trend = parse_trend_answer(req.message)
            if trend:
                state["trend"] = trend
        state["awaiting_trend"] = None

        # Record patient context if explicitly provided this turn (takes
        # priority over the free-text inference above).
        if req.subject:
            state["subject"] = req.subject
        if req.age is not None:
            state["age"] = req.age
        if req.is_pregnant is not None:
            state["is_pregnant"] = req.is_pregnant

        # Accumulate any reports referenced across turns of this conversation
        report_ids = list(dict.fromkeys(state.get("report_ids", []) + req.report_ids))
        state["report_ids"] = report_ids
        report_context = [
            text
            for rid in report_ids
            if (text := self.reports.report_context_text(rid)) is not None
        ]

        # 3. Symptom extraction (merge into state)
        existing = [Symptom(**s) for s in state.get("symptoms", [])]
        new = self.symptoms.extract(req.message)
        merged = self.symptoms.merge(existing, new)
        if not new and merged:
            # This message named no symptom of its own — it's very likely a
            # bare follow-up answer (e.g. "severity is 8 out of 10, lasted 2
            # days"). Apply any severity/duration/onset it mentions to the
            # symptom the question engine is actually focused on (same
            # priority order as next_question: most severe first), instead of
            # silently discarding an answer just because it didn't restate
            # the symptom's name.
            followup = self.symptoms.extract_followup_attributes(req.message)
            if any(followup.values()):
                target = sorted(
                    merged, key=lambda s: (s.severity or 0), reverse=True
                )[0]
                if followup["severity"] is not None:
                    target.severity = followup["severity"]
                if followup["duration"]:
                    target.duration = followup["duration"]
                if followup["onset"]:
                    target.onset = followup["onset"]
        state["symptoms"] = [s.model_dump() for s in merged]

        # 4. Safety engine over the FULL user-side conversation (cumulative)
        user_messages = [
            m["content"]
            for m in self.store.get_messages(conversation_id)
            if m["role"] == "user"
        ]
        verdict = self.safety.evaluate_conversation(user_messages)

        # If the child/infant special flag already fired from the wording used
        # ("my son...", "my baby..."), the subject is already known — skip
        # asking the "is this for you or someone else?" context question.
        if "subject" not in state and (
            "infant" in verdict.special_flags or "child" in verdict.special_flags
        ):
            state["subject"] = "someone_else"

        # Tighten thresholds for special populations (PRD sections 31, 33)
        verdict = self._apply_special_population_rules(verdict, state)
        # A reported worsening (or unchanged) trend genuinely changes how
        # urgently care should be sought, independent of the LLM.
        verdict = self._apply_trend_rules(verdict, state)

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

        # Decide the single next question for this turn now (context question
        # takes priority over a symptom follow-up) so we can tell the LLM
        # exactly what will be asked instead of letting it invent its own,
        # possibly conflicting, question on top.
        follow_up = context_q or self.questions.next_question(
            merged, state.get("questions_asked", [])
        )
        if follow_up == TREND_QUESTION:
            state["awaiting_trend"] = True

        # 8. RAG retrieval (fold in any uploaded-report context for grounding).
        # A message that was purely answering a context question (e.g. "it's
        # for my son") carries no clinical signal, so query on the known
        # symptoms alone rather than diluting/derailing retrieval with it.
        query_message = req.message if not awaiting_context else ""
        query = self.rag.build_query(query_message, merged)
        # Age materially changes what's likely and what's urgent (e.g. a
        # "sudden severe headache" reads differently for an infant vs an
        # adult) — fold it into retrieval too, not just the safety floor.
        age_descriptor = _age_descriptor(state.get("age"))
        if age_descriptor:
            query = f"{query} {age_descriptor}"
        if report_context:
            query = f"{query} {' '.join(report_context)}"
        evidence = await self.rag.retrieve(query)
        sources = self.rag.to_sources(evidence)
        possible = self._possible_explanations(evidence, merged, state)

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
            report_context=report_context,
            answered_context_question=CONTEXT_QUESTIONS.get(awaiting_context),
            pending_follow_up=follow_up,
            patient_age=state.get("age"),
        )
        llm_text = await self.llm.generate(
            SYSTEM_PROMPT,
            user_prompt,
            fallback=build_grounded_fallback(
                evidence, merged, skip_intro=bool(context_ack)
            ),
        )

        # 10. Output safety validation
        safe_text = self.validator.sanitize(llm_text)
        if context_ack:
            safe_text = f"{context_ack} {safe_text}"

        # 11. Record the follow-up as asked
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
            recommended_action=self._recommended_action_for(verdict, state),
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

    def _apply_trend_rules(self, verdict: SafetyVerdict, state: dict) -> SafetyVerdict:
        """A worsening — or flatly unchanged — trend is itself a safety signal,
        not just conversational color: "getting worse" means seek care sooner
        regardless of the original risk level, and "staying the same" means
        it's not resolving on its own and needs attention rather than more
        waiting. Monotonic, like every other floor here — never lowers risk.
        """
        trend = state.get("trend")
        floor = None
        if trend == "worse":
            floor = RiskLevel.URGENT
        elif trend == "same":
            floor = RiskLevel.ROUTINE

        if floor and verdict.risk_level.rank < floor.rank:
            verdict.risk_level = floor
            verdict.is_emergency = floor == RiskLevel.EMERGENCY
        return verdict

    def _recommended_action_for(self, verdict: SafetyVerdict, state: dict) -> str:
        action = recommended_action(verdict.risk_level)
        trend = state.get("trend")
        if not trend:
            return action
        symptoms = state.get("symptoms", [])
        primary = max(symptoms, key=lambda s: s.get("severity") or 0, default=None)
        primary_name = primary.get("name") if primary else None
        trend_action = trend_recommended_action(trend, primary_name)
        return f"{action} {trend_action}" if trend_action else action

    def _pending_context_question(
        self, state: dict, verdict: SafetyVerdict
    ) -> Optional[str]:
        if "subject" not in state:
            state["awaiting_context"] = "subject"
            return CONTEXT_QUESTIONS["subject"]
        if state.get("subject") == "someone_else" and "age" not in state:
            state["awaiting_context"] = "age"
            return CONTEXT_QUESTIONS["age"]
        if "pregnancy" in verdict.special_flags and state.get("is_pregnant") is None:
            state["awaiting_context"] = "pregnancy"
            return CONTEXT_QUESTIONS["pregnancy"]
        return None

    def _consume_context_answer(self, state: dict, message: str) -> None:
        """Interpret this message as the answer to last turn's pending context
        question (if any), so the same question is never re-asked (PRD section 33).

        Explicitly set to None rather than popped: SupabaseStore.upsert_assessment
        merges onto a freshly re-fetched copy of the existing row, so a key that's
        merely *absent* from this turn's state dict doesn't get cleared — the
        stale value from the DB silently wins the merge again. Setting it to None
        keeps the key present so the merge actually overwrites it, otherwise this
        question is treated as still "awaiting" forever: every later message gets
        reinterpreted as its answer (corrupting subject/age/pregnancy) and the
        same acknowledgment gets prepended to every subsequent reply.
        """
        awaiting = state.get("awaiting_context")
        state["awaiting_context"] = None
        if not awaiting:
            return
        value = parse_context_answer(awaiting, message)
        if awaiting == "subject":
            state["subject"] = value
        elif awaiting == "age":
            # Record the attempt even on a failed parse so the question isn't
            # asked again indefinitely; the risk floor logic already treats a
            # missing age as "unknown" safely.
            state["age"] = value
        elif awaiting == "pregnancy":
            state["is_pregnant"] = value

    def _context_answer_ack(self, awaiting: Optional[str], state: dict) -> Optional[str]:
        """A short, deterministic acknowledgment of a just-answered context
        question, prepended to the reply so the conversation visibly responds
        to what the user just said (e.g. who the symptoms are for) instead of
        the LLM treating a contentless answer like "it's for my son" as a new
        symptom description with nothing to react to.
        """
        if awaiting == "subject":
            if state.get("subject") == "someone_else":
                return "Got it, thanks — this assessment is for someone else."
            return "Got it, thanks — this assessment is for you."
        if awaiting == "age":
            age = state.get("age")
            return (
                f"Thanks, noted their age as {age}."
                if age is not None
                else "Thanks — I couldn't quite catch an age there, but let's continue."
            )
        if awaiting == "pregnancy":
            return "Thanks, noted."
        return None

    def _possible_explanations(
        self, evidence: list, symptoms: list[Symptom], state: dict
    ) -> list[str]:
        """Derive possible categories from retrieved evidence titles, narrowing
        the list as more clinical detail is known.

        `evidence` is already ranked best-first by RAGService, so capping the
        list length is enough to keep only the strongest matches — the whole
        point is that the differential actually narrows as the conversation
        goes on instead of showing the same 5 titles turn after turn. "Known"
        detail = the core follow-up attributes on the primary symptom, plus
        the two conversation-level context questions (age, trend).
        """
        ordered = sorted(symptoms, key=lambda s: (s.severity or 0), reverse=True)
        primary = ordered[0] if ordered else None
        known = 0
        if primary:
            known += sum(
                1
                for attr in ("severity", "duration", "onset")
                if getattr(primary, attr, None)
            )
        if state.get("age") is not None:
            known += 1
        if state.get("trend"):
            known += 1
        limit = max(2, 5 - known)

        seen = []
        for e in evidence:
            title = (e.title or "").strip()
            if title and title not in seen:
                seen.append(title)
        return seen[:limit]

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
