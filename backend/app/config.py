"""Application configuration loaded from environment variables.

Secrets (service-role key, LLM key) are read here on the server only and must
never be shipped to the React frontend (see PRD sections 22 and 27).
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    app_env: str = "development"
    app_name: str = "Health RAG Chatbot"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # --- Supabase (optional: app falls back to in-memory store when unset) ---
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None

    # --- LLM ---
    # provider: "anthropic" | "openai" | "none" (deterministic fallback)
    llm_provider: str = "none"
    llm_api_key: Optional[str] = None
    llm_model: str = "claude-opus-4-8"
    llm_base_url: Optional[str] = None  # for openai-compatible gateways

    # --- Embeddings ---
    # provider: "openai" | "local" (deterministic hashing fallback)
    embedding_provider: str = "local"
    embedding_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: Optional[str] = None
    embedding_dimensions: int = 1536

    # --- RAG retrieval tuning (PRD section 14) ---
    retrieval_top_k_vector: int = 20
    retrieval_top_k_final: int = 5
    retrieval_min_score: float = 0.0

    # --- Rate limiting (PRD section 40) ---
    rate_limit_anonymous_per_hour: int = 20
    rate_limit_authenticated_per_hour: int = 100

    # --- Emergency contact (PRD section 32; configurable per region) ---
    emergency_number: str = "your local emergency number"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
