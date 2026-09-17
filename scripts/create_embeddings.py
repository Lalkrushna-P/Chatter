"""Chunk approved documents and write embeddings to Supabase (PRD section 12).

For every APPROVED/PUBLISHED document without chunks, this splits the content,
generates embeddings via the backend EmbeddingService, and inserts rows into
`medical_chunks`.

Usage:
    python scripts/create_embeddings.py

Requires Supabase env vars. Uses EMBEDDING_PROVIDER (openai or local).
"""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Make the backend package importable.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.repositories.store import _chunk_document  # noqa: E402
from app.services.embedding_service import EmbeddingService  # noqa: E402


async def main() -> None:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set. Aborting.")
        return

    from supabase import create_client

    client = create_client(url, key)
    embedder = EmbeddingService()

    docs = (
        client.table("medical_documents")
        .select("*")
        .in_("status", ["APPROVED", "PUBLISHED"])
        .execute()
    ).data or []

    total = 0
    for doc in docs:
        existing = (
            client.table("medical_chunks")
            .select("id")
            .eq("document_id", doc["id"])
            .limit(1)
            .execute()
        ).data
        if existing:
            print(f"Skipping {doc['title']} (already has chunks)")
            continue

        chunks = _chunk_document(doc["content"])
        embeddings = await embedder.embed_batch(chunks)
        rows = [
            {
                "document_id": doc["id"],
                "content": chunk,
                "embedding": embedding,
                "metadata": {
                    "title": doc["title"],
                    "source": doc.get("source"),
                    "source_url": doc.get("source_url"),
                    "category": doc.get("category"),
                    "review_status": (doc.get("metadata") or {}).get("review_status", "approved"),
                },
            }
            for chunk, embedding in zip(chunks, embeddings)
        ]
        client.table("medical_chunks").insert(rows).execute()
        total += len(rows)
        print(f"Embedded {doc['title']}: {len(rows)} chunks")

    print(f"Done. Inserted {total} chunks.")


if __name__ == "__main__":
    asyncio.run(main())
