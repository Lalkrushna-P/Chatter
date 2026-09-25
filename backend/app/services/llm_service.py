"""LLM integration (PRD sections 15, 44).

Providers:
  - "anthropic": Anthropic Messages API via httpx.
  - "openai":    OpenAI-compatible Chat Completions via httpx.
  - "none":      deterministic template response — no keys required. Lets the full
                 pipeline run and be tested offline. Clearly not production-grade
                 language generation.
"""
import httpx

from app.config import Settings, get_settings


class LLMService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    async def generate(
        self, system_prompt: str, user_prompt: str, fallback: str | None = None
    ) -> str:
        provider = self.settings.llm_provider
        try:
            if provider == "anthropic" and self.settings.llm_api_key:
                return await self._generate_anthropic(system_prompt, user_prompt)
            if provider == "openai" and self.settings.llm_api_key:
                return await self._generate_openai(system_prompt, user_prompt)
        except Exception as exc:
            # Never let an LLM-provider failure (bad key, bad model, rate limit,
            # network error, timeout) take down the whole response — the safety
            # engine and RAG evidence are the clinically important part and must
            # still reach the user (see README "Key architecture principle").
            print(f"[llm_service] provider '{provider}' call failed ({exc}); using fallback text")
        return fallback or self._generate_fallback(user_prompt)

    async def _generate_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        url = (self.settings.llm_base_url or "https://api.anthropic.com") + "/v1/messages"
        headers = {
            "x-api-key": self.settings.llm_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": self.settings.llm_model,
            "max_tokens": 700,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return "".join(
            block.get("text", "") for block in data.get("content", [])
        ).strip()

    async def _generate_openai(self, system_prompt: str, user_prompt: str) -> str:
        base = self.settings.llm_base_url or "https://api.openai.com/v1"
        url = f"{base.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        payload = {
            "model": self.settings.llm_model,
            "max_tokens": 700,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _generate_fallback(self, user_prompt: str) -> str:
        """Deterministic reply used when no LLM key is configured.

        The safety engine + response builder already carry the clinically
        important content; this just produces readable connective text.
        """
        return (
            "Thanks for sharing that. I want to understand your symptoms a bit "
            "better so I can help assess how urgent this may be. Please answer the "
            "follow-up question below. Remember, this is general guidance and not a "
            "diagnosis or a substitute for a qualified healthcare professional."
        )
