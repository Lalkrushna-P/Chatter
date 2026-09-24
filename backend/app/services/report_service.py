"""Medical-report analysis orchestration.

Mirrors ConversationManager's pipeline: extraction -> deterministic flagging
-> RAG grounding -> LLM explanation -> output-safety sanitization. Clinical
flagging is deterministic (app.safety.lab_ranges) so it never depends solely
on the LLM, matching this project's core safety principle.
"""
from app.config import Settings, get_settings
from app.prompts.system_prompts import REPORT_SYSTEM_PROMPT, build_report_prompt
from app.repositories.store import InMemoryStore, get_store
from app.safety.lab_ranges import LabValue, extract_lab_values, worst_flag
from app.schemas.common import RiskLevel, Source
from app.schemas.report import LabValueOut, ReportAnalysis
from app.services.llm_service import LLMService
from app.services.rag_service import RAGService
from app.services.report_extraction import extract_text
from app.services.response_builder import DISCLAIMER, OutputSafetyValidator, recommended_action

_FLAG_TO_RISK = {
    "high": RiskLevel.ROUTINE,
    "low": RiskLevel.ROUTINE,
    None: RiskLevel.SELF_CARE,
}


class ReportService:
    def __init__(
        self,
        settings: Settings | None = None,
        store: InMemoryStore | None = None,
    ):
        self.settings = settings or get_settings()
        self.store = store or get_store()
        self.rag = RAGService(self.settings, self.store)
        self.llm = LLMService(self.settings)
        self.validator = OutputSafetyValidator(self.settings)

    async def analyze_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
        conversation_id: str | None,
    ) -> ReportAnalysis:
        text = extract_text(filename, content_type, data)
        flagged = extract_lab_values(text)

        evidence = await self._retrieve_evidence(flagged, text)
        sources = self.rag.to_sources(evidence)
        possible = self._possible_explanations(evidence)

        user_prompt = build_report_prompt(
            filename=filename,
            extracted_text=text,
            flagged_values=flagged,
            evidence=evidence,
        )
        llm_text = await self.llm.generate(
            REPORT_SYSTEM_PROMPT, user_prompt, fallback=self._fallback_summary(flagged)
        )
        summary = self.validator.sanitize(llm_text)

        risk = _FLAG_TO_RISK[worst_flag(flagged)]

        record = self.store.create_report(
            conversation_id=conversation_id,
            filename=filename,
            content_type=content_type,
            extracted_text=text,
            analysis={
                "summary": summary,
                "flagged_values": [v.__dict__ for v in flagged],
                "possible_categories": possible,
                "risk_level": risk.value,
                "sources": [s.model_dump() for s in sources],
            },
            risk_level=risk.value,
            raw_bytes=data,
        )

        return ReportAnalysis(
            report_id=record["id"],
            conversation_id=conversation_id,
            filename=filename,
            summary=summary,
            flagged_values=[LabValueOut(**v.__dict__) for v in flagged],
            possible_categories=possible,
            risk_level=risk,
            recommended_action=recommended_action(risk),
            sources=sources,
            disclaimer=DISCLAIMER,
        )

    def get_analysis(self, report_id: str) -> ReportAnalysis | None:
        record = self.store.get_report(report_id)
        if record is None:
            return None
        analysis = record.get("analysis", {})
        risk = RiskLevel(record.get("risk_level", "unknown"))
        return ReportAnalysis(
            report_id=record["id"],
            conversation_id=record.get("conversation_id"),
            filename=record.get("filename", ""),
            summary=analysis.get("summary", ""),
            flagged_values=[LabValueOut(**v) for v in analysis.get("flagged_values", [])],
            possible_categories=analysis.get("possible_categories", []),
            risk_level=risk,
            recommended_action=recommended_action(risk),
            sources=[Source(**s) for s in analysis.get("sources", [])],
            disclaimer=DISCLAIMER,
        )

    def report_context_text(self, report_id: str) -> str | None:
        """Short text summary of a stored report, for folding into chat context."""
        record = self.store.get_report(report_id)
        if record is None:
            return None
        analysis = record.get("analysis", {})
        flags = analysis.get("flagged_values", [])
        flags_text = ", ".join(
            f"{f['name']} {f['flag']} ({f['value']} {f['unit']})"
            for f in flags
            if f.get("flag") != "normal"
        ) or "no abnormal values flagged"
        return (
            f"Report '{record.get('filename', 'uploaded report')}': "
            f"{analysis.get('summary', '')} Flagged values: {flags_text}."
        )

    def _fallback_summary(self, flagged: list[LabValue]) -> str:
        """Deterministic connective text used when no LLM key is configured.

        The flagged-values list already carries the clinically important
        content (see app.safety.lab_ranges); this is just readable framing.
        """
        abnormal = [v for v in flagged if v.flag != "normal"]
        if not abnormal:
            return (
                "We reviewed your uploaded report and didn't find any values outside "
                "the reference ranges we check. Please still discuss the full report "
                "with a qualified healthcare professional, as this automated check is "
                "not a substitute for their review."
            )
        names = ", ".join(f"{v.name} ({v.flag})" for v in abnormal)
        return (
            f"We reviewed your uploaded report and flagged the following value(s) as "
            f"outside the typical reference range: {names}. This is general guidance, "
            "not a diagnosis — please share the full report with a qualified "
            "healthcare professional to interpret what it means for you."
        )

    async def _retrieve_evidence(self, flagged: list[LabValue], text: str) -> list:
        """Retrieve evidence per abnormal value rather than one blended query.

        Lab-reference docs share a lot of boilerplate phrasing ("seek prompt
        medical follow-up for an abnormal X result"), which dilutes the
        lexical-overlap reranker when several flagged values are combined into
        a single query — the test-specific document (e.g. creatinine/kidney)
        can get crowded out by generic overlap with unrelated lab docs. One
        retrieval per flagged value keeps each grounded in its own evidence.
        """
        abnormal = [v for v in flagged if v.flag != "normal"]
        if not abnormal:
            return await self.rag.retrieve(text[:500])

        seen_titles: set[str] = set()
        combined: list = []
        for value in abnormal:
            per_value = await self.rag.retrieve(f"{value.name} {value.flag}")
            for chunk in per_value[:2]:  # best 1-2 matches for THIS value
                if chunk.title in seen_titles:
                    continue
                seen_titles.add(chunk.title)
                combined.append(chunk)
        return combined

    def _possible_explanations(self, evidence: list) -> list[str]:
        seen: list[str] = []
        for e in evidence:
            title = (e.title or "").strip()
            if title and title not in seen:
                seen.append(title)
        return seen[:5]
