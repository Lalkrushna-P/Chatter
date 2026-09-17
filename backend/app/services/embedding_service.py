"""Embedding generation (PRD sections 12, 44).

Two providers:
  - "openai": calls an OpenAI-compatible embeddings endpoint via httpx.
  - "local":  deterministic hashing embedding — no network, no keys. Good enough
              for local development and demos; NOT for production retrieval
              quality.
"""
import hashlib
import math

import httpx

from app.config import Settings, get_settings


class EmbeddingService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.dim = self.settings.embedding_dimensions

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self.settings.embedding_provider == "openai" and self.settings.embedding_api_key:
            return await self._embed_openai(texts)
        return [self._embed_local(t) for t in texts]

    # --- Real provider ---------------------------------------------------
    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        base = self.settings.embedding_base_url or "https://api.openai.com/v1"
        url = f"{base.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {self.settings.embedding_api_key}"}
        payload = {"model": self.settings.embedding_model, "input": texts}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]

    # --- Deterministic local fallback ------------------------------------
    def _embed_local(self, text: str) -> list[float]:
        """Hash tokens into a fixed-dimension bag-of-words vector, L2-normalized.

        Deterministic and dependency-free. Captures lexical overlap well enough
        for demos of semantic-ish retrieval.
        """
        vec = [0.0] * self.dim
        tokens = _tokenize(text)
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 7) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def _tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]+", text.lower())


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
