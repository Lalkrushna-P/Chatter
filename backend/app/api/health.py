"""Health/observability endpoints (PRD section 41)."""
from fastapi import APIRouter

from app.config import get_settings
from app.repositories.store import get_store

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict:
    settings = get_settings()
    store = get_store()
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "supabase_enabled": settings.supabase_enabled,
        "knowledge_chunks_loaded": store.count_chunks(),
    }
