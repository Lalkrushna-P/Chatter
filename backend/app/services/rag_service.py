"""Retrieval-Augmented Generation pipeline (PRD sections 10, 14).

Flow:
  query generation -> embedding -> vector search (top 20)
    -> metadata filtering -> rerank -> top 5 evidence chunks
"""
from dataclasses import dataclass
from typing import Optional

from app.config import Settings, get_settings
from app.repositories.store import InMemoryStore, get_store
from app.schemas.common import Source, Symptom
from app.services.embedding_service import EmbeddingService


@dataclass
class EvidenceChunk:
    content: str
    title: Optional[str]
    source: Optional[str]
    source_url: Optional[str]
    category: Optional[str]
    score: float


class RAGService:
    def __init__(
        self,
        settings: Settings | None = None,
        store: InMemoryStore | None = None,
        embedder: EmbeddingService | None = None,
    ):
        self.settings = settings or get_settings()
        self.store = store or get_store()
        self.embedder = embedder or EmbeddingService(self.settings)

    def build_query(self, message: str, symptoms: list[Symptom]) -> str:
        """Combine the user's message with structured symptoms into a retrieval query.

        Folds in every attribute extracted so far (not just location/severity) —
        duration, onset, frequency, and trigger/relieving/worsening factors are
        exactly the clinically differentiating detail follow-up answers add
        (e.g. "sudden" vs "gradual" onset separates thunderclap headache from
        tension-type). Without them here, each answer only helped retrieval for
        the one turn it was mentioned in, so the possible-explanations list
        never actually narrowed as the conversation progressed.
        """
        parts = [message]
        for s in symptoms:
            fragment = s.name
            if s.location:
                fragment += f" {s.location}"
            if s.severity is not None:
                fragment += f" severity {s.severity}"
            if s.duration:
                fragment += f" duration {s.duration}"
            if s.onset:
                fragment += f" onset {s.onset}"
            if s.frequency:
                fragment += f" frequency {s.frequency}"
            if s.trigger:
                fragment += f" trigger {s.trigger}"
            if s.relieving_factors:
                fragment += f" relieved by {s.relieving_factors}"
            if s.worsening_factors:
                fragment += f" worse with {s.worsening_factors}"
            parts.append(fragment)
            parts.extend(s.associated_symptoms)
        return " ".join(parts)

    async def retrieve(
        self,
        query: str,
        category: Optional[str] = None,
    ) -> list[EvidenceChunk]:
        query_embedding = await self.embedder.embed(query)

        # Stage 1: vector search (top N)
        raw = await self.store.match_chunks(
            query_embedding,
            top_k=self.settings.retrieval_top_k_vector,
            category=category,
            approved_only=True,
        )

        # Stage 2: score threshold filter
        filtered = [
            c for c in raw
            if c.get("score", 0.0) >= self.settings.retrieval_min_score
        ]

        # Stage 3: rerank (keyword-overlap boost on top of vector score)
        reranked = self._rerank(query, filtered)

        # Stage 4: take top-K final
        top = reranked[: self.settings.retrieval_top_k_final]
        return [self._to_evidence(c) for c in top]

    def _rerank(self, query: str, chunks: list[dict]) -> list[dict]:
        query_terms = set(_terms(query))
        rescored = []
        for c in chunks:
            overlap = len(query_terms & set(_terms(c["content"])))
            boost = overlap / (len(query_terms) or 1)
            combined = 0.7 * c.get("score", 0.0) + 0.3 * boost
            rescored.append((combined, overlap, c))
        rescored.sort(key=lambda x: x[0], reverse=True)

        # If any chunk shares vocabulary with the query, drop the zero-overlap
        # chunks: with the deterministic local embedding, lexical overlap is the
        # more trustworthy relevance signal, and this keeps the differential list
        # tight and on-topic (PRD sections 14, 17). A real embedding model makes
        # this filter largely redundant.
        has_overlap = [item for item in rescored if item[1] > 0]
        chosen = has_overlap if has_overlap else rescored
        return [c for _, _, c in chosen]

    def _to_evidence(self, chunk: dict) -> EvidenceChunk:
        meta = chunk.get("metadata", {})
        return EvidenceChunk(
            content=chunk["content"],
            title=meta.get("title"),
            source=meta.get("source"),
            source_url=meta.get("source_url"),
            category=meta.get("category"),
            score=chunk.get("score", 0.0),
        )

    @staticmethod
    def to_sources(evidence: list[EvidenceChunk]) -> list[Source]:
        seen = set()
        sources = []
        for e in evidence:
            key = (e.title, e.source)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                Source(
                    title=e.title or "Medical reference",
                    source=e.source,
                    source_url=e.source_url,
                    category=e.category,
                )
            )
        return sources


_STOPWORDS = {
    "the", "and", "for", "have", "has", "had", "was", "are", "you", "your",
    "with", "this", "that", "feel", "feeling", "been", "very", "but", "not",
    "any", "can", "could", "would", "should", "get", "got", "getting", "since",
    "from", "some", "also", "just", "like", "about", "around", "over", "than",
    "then", "them", "they", "there", "here", "what", "when", "where", "how",
    "out", "day", "days", "bad", "lot", "really", "still", "now", "today",
    "yesterday", "morning", "night", "pain",  # 'pain' too common across docs
}


def _terms(text: str) -> list[str]:
    import re

    return [
        t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 2 and t not in _STOPWORDS
    ]
