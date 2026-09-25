"""Medical report upload & analysis endpoints."""
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.config import get_settings
from app.schemas.report import ReportAnalysis, ReportUploadResponse
from app.services.report_extraction import SUPPORTED_EXTENSIONS, OCRUnavailableError
from app.services.report_service import ReportService
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api/reports", tags=["reports"])
_service = ReportService()


@router.post("/upload", response_model=ReportUploadResponse)
async def upload_report(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
) -> ReportUploadResponse:
    enforce_rate_limit(request, authenticated=False)
    settings = get_settings()

    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
        )

    data = await file.read()
    max_bytes = settings.report_max_file_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {settings.report_max_file_size_mb} MB.",
        )

    try:
        analysis = await _service.analyze_upload(
            filename=file.filename,
            content_type=file.content_type,
            data=data,
            conversation_id=conversation_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return analysis


@router.get("/{report_id}", response_model=ReportAnalysis)
async def get_report(report_id: str) -> ReportAnalysis:
    analysis = _service.get_analysis(report_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return analysis
