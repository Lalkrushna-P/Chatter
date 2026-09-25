"""Storage layer abstraction.

Provides a single `Store` protocol with two implementations:
  - InMemoryStore: default; requires no external services. Seeds medical chunks
    from knowledge-base/metadata so RAG works immediately.
  - SupabaseStore: uses the Supabase Python client with the service-role key
    (server-side only). Vector search uses a Postgres RPC `match_medical_chunks`
    (see database/schema.sql).

The active store is chosen at startup based on config.supabase_enabled.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import Settings, get_settings
from app.services.embedding_service import cosine_similarity


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------
class InMemoryStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.conversations: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.assessments: dict[str, dict] = {}
        self.feedback: list[dict] = []
        self.chunks: list[dict] = []  # {id, document_id, content, embedding, metadata}
        self.documents: dict[str, dict] = {}
        self.reports: dict[str, dict] = {}

    # --- Conversations ---
    def create_conversation(self, user_id: Optional[str]) -> dict:
        cid = _new_id()
        conv = {
            "id": cid,
            "user_id": user_id,
            "status": "active",
            "risk_level": "unknown",
            "started_at": _now(),
            "ended_at": None,
        }
        self.conversations[cid] = conv
        self.messages[cid] = []
        return conv

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        return self.conversations.get(conversation_id)

    def update_conversation(self, conversation_id: str, **fields) -> None:
        conv = self.conversations.get(conversation_id)
        if conv:
            conv.update(fields)

    # --- Messages ---
    def add_message(self, conversation_id: str, role: str, content: str) -> dict:
        msg = {
            "id": _new_id(),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "created_at": _now(),
        }
        self.messages.setdefault(conversation_id, []).append(msg)
        return msg

    def get_messages(self, conversation_id: str) -> list[dict]:
        return list(self.messages.get(conversation_id, []))

    # --- Assessments ---
    def upsert_assessment(self, conversation_id: str, data: dict) -> dict:
        existing = next(
            (a for a in self.assessments.values() if a["conversation_id"] == conversation_id),
            None,
        )
        if existing:
            existing.update(data)
            return existing
        aid = _new_id()
        rec = {"id": aid, "conversation_id": conversation_id, "created_at": _now(), **data}
        self.assessments[aid] = rec
        return rec

    def get_assessment(self, assessment_id: str) -> Optional[dict]:
        return self.assessments.get(assessment_id)

    def get_assessment_by_conversation(self, conversation_id: str) -> Optional[dict]:
        return next(
            (a for a in self.assessments.values() if a["conversation_id"] == conversation_id),
            None,
        )

    # --- Feedback ---
    def add_feedback(self, conversation_id: str, rating: int, text: Optional[str]) -> dict:
        rec = {
            "id": _new_id(),
            "conversation_id": conversation_id,
            "rating": rating,
            "feedback_text": text,
            "created_at": _now(),
        }
        self.feedback.append(rec)
        return rec

    # --- Medical reports ---
    def create_report(
        self,
        *,
        conversation_id: Optional[str],
        filename: str,
        content_type: Optional[str],
        extracted_text: str,
        analysis: dict,
        risk_level: str,
        raw_bytes: Optional[bytes] = None,
    ) -> dict:
        rid = _new_id()
        rec = {
            "id": rid,
            "conversation_id": conversation_id,
            "filename": filename,
            "content_type": content_type,
            "extracted_text": extracted_text,
            "analysis": analysis,
            "risk_level": risk_level,
            "status": "completed",
            "created_at": _now(),
        }
        self.reports[rid] = rec
        return rec

    def get_report(self, report_id: str) -> Optional[dict]:
        return self.reports.get(report_id)

    def update_report(self, report_id: str, **fields) -> None:
        rec = self.reports.get(report_id)
        if rec:
            rec.update(fields)

    # --- Knowledge base / vector search ---
    def add_chunk(self, chunk: dict) -> None:
        self.chunks.append(chunk)

    def seed_chunks(self, chunks: list[dict]) -> None:
        self.chunks.extend(chunks)

    def count_chunks(self) -> int:
        return len(self.chunks)

    async def match_chunks(
        self,
        query_embedding: list[float],
        top_k: int,
        category: Optional[str] = None,
        approved_only: bool = True,
    ) -> list[dict]:
        results = []
        for chunk in self.chunks:
            meta = chunk.get("metadata", {})
            if approved_only and meta.get("review_status") not in ("approved", "published", None):
                # Only approved/published documents are usable (PRD section 30).
                if meta.get("review_status") not in ("approved", "published"):
                    continue
            if category and meta.get("category") != category:
                continue
            score = cosine_similarity(query_embedding, chunk["embedding"])
            results.append((score, chunk))
        results.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, chunk in results[:top_k]:
            item = dict(chunk)
            item["score"] = score
            out.append(item)
        return out


# ---------------------------------------------------------------------------
# Supabase implementation
# ---------------------------------------------------------------------------
class SupabaseStore(InMemoryStore):
    """Supabase-backed store. Falls back to in-memory behavior for anything not
    yet persisted so the app never hard-crashes on a transient DB issue."""

    def __init__(self, settings: Settings | None = None):
        super().__init__(settings)
        from supabase import create_client  # imported lazily

        self.client = create_client(
            self.settings.supabase_url,
            self.settings.supabase_service_role_key,
        )

    def create_conversation(self, user_id: Optional[str]) -> dict:
        conv = {"user_id": user_id, "status": "active", "risk_level": "unknown"}
        res = self.client.table("conversations").insert(conv).execute()
        return res.data[0]

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        res = (
            self.client.table("conversations")
            .select("*").eq("id", conversation_id).limit(1).execute()
        )
        return res.data[0] if res.data else None

    def update_conversation(self, conversation_id: str, **fields) -> None:
        self.client.table("conversations").update(fields).eq("id", conversation_id).execute()

    def add_message(self, conversation_id: str, role: str, content: str) -> dict:
        row = {"conversation_id": conversation_id, "role": role, "content": content}
        res = self.client.table("messages").insert(row).execute()
        return res.data[0]

    def get_messages(self, conversation_id: str) -> list[dict]:
        res = (
            self.client.table("messages")
            .select("*").eq("conversation_id", conversation_id)
            .order("created_at").execute()
        )
        return res.data or []

    def add_feedback(self, conversation_id: str, rating: int, text: Optional[str]) -> dict:
        row = {"conversation_id": conversation_id, "rating": rating, "feedback_text": text}
        res = self.client.table("feedback").insert(row).execute()
        return res.data[0]

    def upsert_assessment(self, conversation_id: str, data: dict) -> dict:
        """Persist the running conversation state to the `assessments` table.

        `data` is often a partial update (e.g. `{"status": "completed"}`), so it
        must be merged onto the existing record rather than replacing it — the
        in-memory version does this via dict.update(); this mirrors that. The
        full state dict (including fields with no dedicated column, like
        questions_asked/subject/age/report_ids) is stored verbatim in the
        `state` jsonb column; a few fields are also mirrored into their own
        columns for direct SQL querying.
        """
        existing = self.get_assessment_by_conversation(conversation_id)
        merged = {**(existing or {}), **data}
        row = {
            "conversation_id": conversation_id,
            "symptoms": merged.get("symptoms", []),
            "risk_level": merged.get("risk_level", "unknown"),
            "possible_explanations": merged.get("possible_explanations", []),
            "red_flags": merged.get("red_flags", []),
            "status": merged.get("status", "active"),
            "state": merged,
        }
        if existing:
            res = (
                self.client.table("assessments")
                .update(row).eq("id", existing["id"]).execute()
            )
        else:
            res = self.client.table("assessments").insert(row).execute()
        return self._assessment_row_to_state(res.data[0])

    def get_assessment(self, assessment_id: str) -> Optional[dict]:
        res = (
            self.client.table("assessments")
            .select("*").eq("id", assessment_id).limit(1).execute()
        )
        return self._assessment_row_to_state(res.data[0]) if res.data else None

    def get_assessment_by_conversation(self, conversation_id: str) -> Optional[dict]:
        res = (
            self.client.table("assessments")
            .select("*").eq("conversation_id", conversation_id)
            .limit(1).execute()
        )
        return self._assessment_row_to_state(res.data[0]) if res.data else None

    @staticmethod
    def _assessment_row_to_state(row: dict) -> dict:
        state = dict(row.get("state") or {})
        state["id"] = row["id"]
        state["conversation_id"] = row["conversation_id"]
        # Structured columns are the source of truth if the state blob and the
        # columns ever disagree (e.g. a row edited directly in the dashboard).
        state["symptoms"] = row.get("symptoms") or state.get("symptoms", [])
        state["risk_level"] = row.get("risk_level") or state.get("risk_level", "unknown")
        state["possible_explanations"] = (
            row.get("possible_explanations") or state.get("possible_explanations", [])
        )
        state["red_flags"] = row.get("red_flags") or state.get("red_flags", [])
        state["status"] = row.get("status") or state.get("status", "active")
        return state

    def create_report(
        self,
        *,
        conversation_id: Optional[str],
        filename: str,
        content_type: Optional[str],
        extracted_text: str,
        analysis: dict,
        risk_level: str,
        raw_bytes: Optional[bytes] = None,
    ) -> dict:
        row = {
            "conversation_id": conversation_id,
            "filename": filename,
            "content_type": content_type,
            "extracted_text": extracted_text,
            "analysis": analysis,
            "risk_level": risk_level,
            "status": "completed",
        }
        res = self.client.table("report_documents").insert(row).execute()
        record = res.data[0]

        # Best-effort raw-file upload: a missing/misconfigured Storage bucket
        # should never break the (already-persisted) analysis.
        if raw_bytes is not None:
            try:
                path = f"{record['id']}/{filename}"
                self.client.storage.from_(self.settings.report_storage_bucket).upload(
                    path, raw_bytes
                )
                self.client.table("report_documents").update(
                    {"storage_path": path}
                ).eq("id", record["id"]).execute()
                record["storage_path"] = path
            except Exception as exc:  # pragma: no cover
                print(f"[store] Report storage upload failed ({exc}); text/analysis still saved")

        return record

    def get_report(self, report_id: str) -> Optional[dict]:
        res = (
            self.client.table("report_documents")
            .select("*").eq("id", report_id).limit(1).execute()
        )
        return res.data[0] if res.data else None

    def update_report(self, report_id: str, **fields) -> None:
        self.client.table("report_documents").update(fields).eq("id", report_id).execute()

    async def match_chunks(
        self,
        query_embedding: list[float],
        top_k: int,
        category: Optional[str] = None,
        approved_only: bool = True,
    ) -> list[dict]:
        try:
            res = self.client.rpc(
                "match_medical_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_count": top_k,
                    "filter_category": category,
                },
            ).execute()
            return res.data or []
        except Exception:
            # Fall back to in-memory matching if RPC unavailable.
            return await super().match_chunks(
                query_embedding, top_k, category, approved_only
            )

    def count_chunks(self) -> int:
        try:
            res = self.client.table("medical_chunks").select("id", count="exact").limit(1).execute()
            return res.count or 0
        except Exception:
            return super().count_chunks()


# ---------------------------------------------------------------------------
# Store factory + knowledge-base seeding
# ---------------------------------------------------------------------------
_store: Optional[InMemoryStore] = None


def get_store() -> InMemoryStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.supabase_enabled:
            try:
                _store = SupabaseStore(settings)
            except Exception as exc:  # pragma: no cover
                print(f"[store] Supabase init failed ({exc}); using in-memory store")
                _store = InMemoryStore(settings)
        else:
            _store = InMemoryStore(settings)
    return _store


async def seed_knowledge_base(store: InMemoryStore) -> int:
    """Seed the in-memory store with sample medical chunks + embeddings.

    Reads knowledge-base/metadata/sample_docs.json and embeds each chunk. Only
    runs for the in-memory store (Supabase is seeded via scripts/create_embeddings.py).
    """
    if isinstance(store, SupabaseStore):
        return 0
    if store.chunks:
        return len(store.chunks)

    from app.services.embedding_service import EmbeddingService

    kb_path = _find_kb_file()
    if not kb_path or not kb_path.exists():
        return 0

    docs = json.loads(kb_path.read_text(encoding="utf-8"))
    embedder = EmbeddingService(store.settings)

    count = 0
    for doc in docs:
        doc_id = doc.get("id", _new_id())
        store.documents[doc_id] = doc
        for chunk_text in _chunk_document(doc["content"]):
            embedding = await embedder.embed(chunk_text)
            store.add_chunk(
                {
                    "id": _new_id(),
                    "document_id": doc_id,
                    "content": chunk_text,
                    "embedding": embedding,
                    "metadata": {
                        "title": doc.get("title"),
                        "source": doc.get("source"),
                        "source_url": doc.get("source_url"),
                        "category": doc.get("category"),
                        "review_status": doc.get("review_status", "approved"),
                    },
                }
            )
            count += 1
    return count


def _find_kb_file() -> Optional[Path]:
    # backend/app/repositories/store.py -> repo root is parents[3]
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "knowledge-base" / "metadata" / "sample_docs.json",
        Path.cwd() / "knowledge-base" / "metadata" / "sample_docs.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _chunk_document(text: str, max_chars: int = 900, overlap: int = 150) -> list[str]:
    """Simple paragraph-aware chunking (PRD section 12: ~500-1000 tokens, 10-20% overlap).

    Uses characters as a rough proxy for tokens in this scaffold.
    """
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 <= max_chars:
            current = f"{current}\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            # start new chunk with overlap tail of previous
            tail = current[-overlap:] if current else ""
            current = f"{tail}\n{para}".strip()
    if current:
        chunks.append(current)
    return chunks or [text]
