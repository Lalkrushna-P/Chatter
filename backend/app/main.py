"""FastAPI application entry point (PRD sections 24, 26)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import assessment, chat, feedback, health, reports
from app.config import get_settings
from app.repositories.store import get_store, seed_knowledge_base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed the in-memory knowledge base on startup so RAG works out of the box.
    store = get_store()
    count = await seed_knowledge_base(store)
    if count:
        print(f"[startup] Seeded {count} knowledge-base chunks")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="RAG-based primary health detection & triage chatbot (MVP).",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(assessment.router)
    app.include_router(feedback.router)
    app.include_router(reports.router)

    @app.get("/")
    async def root() -> dict:
        return {"service": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
