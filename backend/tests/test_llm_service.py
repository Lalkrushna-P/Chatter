"""LLM provider failures must never crash the pipeline (see README "Key
architecture principle" — clinical safety can't depend on the LLM)."""
from app.config import Settings
from app.services.llm_service import LLMService


async def test_provider_failure_falls_back_instead_of_raising():
    settings = Settings(
        llm_provider="openai",
        llm_api_key="fake-key",
        llm_base_url="https://127.0.0.1:0",  # nothing listens here -> connection error
    )
    service = LLMService(settings)

    result = await service.generate("system prompt", "user prompt")

    assert isinstance(result, str)
    assert result  # falls back to deterministic connective text, doesn't raise


async def test_custom_fallback_is_used_on_failure():
    settings = Settings(
        llm_provider="anthropic",
        llm_api_key="fake-key",
        llm_base_url="https://127.0.0.1:0",
    )
    service = LLMService(settings)

    result = await service.generate("system prompt", "user prompt", fallback="custom fallback text")

    assert result == "custom fallback text"
