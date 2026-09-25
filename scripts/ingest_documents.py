"""Ingest curated medical documents into Supabase (PRD sections 12, 30).

Reads knowledge-base/metadata/sample_docs.json (or a provided file), inserts each
document into `medical_documents`, and prints the resulting document IDs. Chunking
and embedding are handled by create_embeddings.py.

Usage:
    python scripts/ingest_documents.py [path/to/docs.json]

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment/.env.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
# load_dotenv() with no path resolves relative to this script's own directory
# (scripts/), not the process cwd, so backend/.env (a sibling dir) is never
# found implicitly — point it there explicitly.
load_dotenv(ROOT / "backend" / ".env")

DEFAULT_DOCS = ROOT / "knowledge-base" / "metadata" / "sample_docs.json"


def main() -> None:
    docs_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DOCS
    docs = json.loads(docs_path.read_text(encoding="utf-8"))

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — dry run only.")
        for d in docs:
            print(f"  would insert: {d['title']} [{d.get('category')}]")
        return

    from supabase import create_client

    client = create_client(url, key)

    # Idempotent by title: re-running this script (e.g. after adding new docs
    # to sample_docs.json) must not duplicate documents already ingested.
    existing_titles = {
        row["title"]
        for row in (client.table("medical_documents").select("title").execute().data or [])
    }

    for d in docs:
        if d["title"] in existing_titles:
            print(f"Skipping {d['title']} (already ingested)")
            continue
        row = {
            "title": d["title"],
            "source": d.get("source"),
            "source_url": d.get("source_url"),
            "category": d.get("category"),
            "content": d["content"],
            "version": d.get("version"),
            "status": "APPROVED" if d.get("review_status") == "approved" else "DRAFT",
            "metadata": {
                "review_status": d.get("review_status", "draft"),
                "reviewed_at": d.get("reviewed_at"),
            },
        }
        res = client.table("medical_documents").insert(row).execute()
        print(f"Inserted {d['title']} -> {res.data[0]['id']}")


if __name__ == "__main__":
    main()
