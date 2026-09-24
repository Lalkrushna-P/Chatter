# Chatter — RAG-Based Primary Health Detection Chatbot

An AI-powered conversational **health screening and triage** MVP built to the
product PRD. Users describe symptoms naturally; the system asks follow-up
questions, retrieves grounded medical evidence with RAG, runs a **deterministic
safety/red-flag engine**, and returns a risk level, possible explanations,
recommended next step, and cited sources.

> ⚠️ **This is a screening and guidance tool, not a diagnosis and not a substitute
> for a qualified healthcare professional.** The rule set and sample knowledge base
> are engineering scaffolding and are **not clinically validated**. They must be
> reviewed by qualified clinicians before any real-world use (PRD §18, §50).

---

## Key architecture principle

Medical safety decisions do **not** depend solely on the LLM (PRD §49). The flow is:

```
User → Conversation → Symptom Extraction → Safety / Red-Flag Detection
     → Risk Assessment → RAG Retrieval → Evidence → LLM Response
     → Output Safety Validation → User
```

A rule-based safety engine runs alongside the LLM and can **override** its output
(e.g. force an emergency response and stop questioning).

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | Python + FastAPI + Pydantic |
| Database / Vector | Supabase Postgres + pgvector |
| LLM | Anthropic / OpenAI-compatible (pluggable) |
| Embeddings | OpenAI-compatible or local fallback |
| Deployment | Vercel |

## Runs with zero API keys

For local development and demos the app runs **fully offline**:

- `LLM_PROVIDER=none` → deterministic connective text (safety + retrieval carry the clinical content).
- `EMBEDDING_PROVIDER=local` → deterministic hashing embeddings.
- No Supabase → in-memory store, seeded from `knowledge-base/metadata/sample_docs.json`.

Set real providers via env vars for production quality.

---

## Repository layout

```
Chatter/
├── backend/            FastAPI app (api, services, safety, repositories, prompts)
├── frontend/           React + Vite chat UI
├── database/           Supabase schema.sql (tables, pgvector RPC, RLS)
├── knowledge-base/     Curated medical docs (raw / processed / metadata)
├── scripts/            ingest_documents.py, create_embeddings.py, evaluate_rag.py
└── README.md
```

See `backend/app/services/` for the pipeline: `safety_service`, `symptom_service`,
`rag_service`, `embedding_service`, `llm_service`, `conversation_service`,
`response_builder`.

---

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    |    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional: fill in Supabase / LLM keys
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env          # leave VITE_API_BASE_URL blank to use the dev proxy
npm run dev                   # http://localhost:5173
```

The Vite dev server proxies `/api` to `http://localhost:8000`.

### 3. Tests & evaluation

```bash
cd backend
pytest                        # unit + pipeline tests (incl. PRD §37 cases)
python ../scripts/evaluate_rag.py   # triage evaluation + emergency sensitivity
```

The evaluation reports **emergency-detection sensitivity** — the metric the PRD
weights most heavily (§51), since a false negative on an emergency is the worst
failure mode.

---

## Report analysis setup (optional — for scanned PDF / image OCR)

Uploading text-based PDFs and DOCX reports works out of the box. Reading
**scanned PDFs or photographed reports** uses local OCR (`pytesseract`), which
needs two system binaries on PATH — they are not pip-installable:

- **Tesseract OCR** — https://github.com/UB-Mannheim/tesseract/wiki (Windows installer)
- **Poppler** (for rendering scanned PDF pages to images) — https://github.com/oschwartz10612/poppler-windows/releases

Without these, text-based PDF/DOCX/plain-image extraction still works; only the
scanned-PDF OCR fallback needs them.

## Supabase setup (optional, for persistence + real vector search)

1. Create a Supabase project and enable the `vector` extension.
2. Run `database/schema.sql` in the SQL editor (tables, `match_medical_chunks`
   RPC, and Row Level Security).
3. Put `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env`
   (service-role key is **server-side only** — never expose to the frontend).
   For report uploads, also create a Storage bucket named `medical-reports`
   (Storage > New bucket in the dashboard — this can't be done via SQL).
4. Load the knowledge base:
   ```bash
   python scripts/ingest_documents.py
   python scripts/create_embeddings.py
   ```

Keep `EMBEDDING_DIMENSIONS` in sync with the `vector(N)` size in `schema.sql`.

---

## API endpoints (PRD §25)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` | Send a message, get triage response |
| POST | `/api/assessment/start` | Create an assessment |
| GET | `/api/assessment/{conversation_id}` | Assessment status |
| GET | `/api/assessment/{conversation_id}/summary` | Structured summary |
| POST | `/api/assessment/{conversation_id}/end` | End & finalize |
| POST | `/api/feedback` | Store user feedback |
| GET | `/api/health` | Health / observability |
| POST | `/api/reports/upload` | Upload a medical report (PDF/DOCX/image) for analysis |
| GET | `/api/reports/{report_id}` | Fetch a stored report analysis |

---

## Safety & guardrails implemented

- **Deterministic red-flag engine** (emergency + urgent rules) that runs
  independently of the LLM and escalates across conversation turns.
- **Emergency short-circuit**: concise action-oriented response, no further
  questioning (§32).
- **Self-harm routing** to crisis-support messaging.
- **Special populations**: pregnancy / infant / child flags raise the risk floor (§33).
- **Output validation**: strips definitive-diagnosis and prescription/dosage
  language before display (§4, §31 Layer 4).
- **Retrieval safety**: only `APPROVED` / `PUBLISHED` documents are used (§30).
- **Prompt-injection resistance**: user messages and retrieved docs are treated as
  data/evidence, not instructions (§39).
- **Rate limiting** (§40) and **RLS** conversation isolation (§28).

## Not implemented (out of MVP scope / needs clinical work)

Admin portal, Supabase Auth UI, multi-language, and a **clinically validated** rule
set + evaluation dataset. The current rules intentionally over-triage and are a
starting point for clinical review (PRD §36, §50).
