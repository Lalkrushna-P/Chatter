"""End-to-end report analysis pipeline test (offline: llm_provider=none,
embedding_provider=local, in-memory store)."""
import io

import docx

from app.services.report_service import ReportService

service = ReportService()


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


async def test_analyze_upload_flags_abnormal_value_and_persists():
    data = _make_docx_bytes(["Lab report", "Fasting Glucose: 160 mg/dL"])
    analysis = await service.analyze_upload(
        filename="labs.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        data=data,
        conversation_id=None,
    )

    assert analysis.report_id
    glucose = next(v for v in analysis.flagged_values if v.name == "fasting glucose")
    assert glucose.flag == "high"
    assert analysis.disclaimer

    fetched = service.get_analysis(analysis.report_id)
    assert fetched is not None
    assert fetched.report_id == analysis.report_id


async def test_report_context_text_summarizes_flags():
    data = _make_docx_bytes(["Creatinine: 2.1 mg/dL"])
    analysis = await service.analyze_upload(
        filename="labs2.docx",
        content_type=None,
        data=data,
        conversation_id=None,
    )
    context = service.report_context_text(analysis.report_id)
    assert context is not None
    assert "creatinine" in context.lower()
