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

## Deploying to Vercel

The backend and frontend deploy as **two separate Vercel projects** from the
same GitHub repo (this isn't a Next.js monorepo, so one project per app root).

### 1. Supabase (do this first)

1. In the Supabase dashboard for your project: **SQL Editor** → paste and run
   `database/schema.sql` (creates tables, the `match_medical_chunks` RPC, and RLS).
2. **Storage** → **New bucket** → name it exactly `medical-reports` (SQL can't
   create Storage buckets, so this is a manual dashboard step).
3. **Project Settings → API** → copy the `service_role` secret key (never the
   `anon` key) for the backend env vars below. Keep it out of any client-side code.
4. Seed the knowledge base into Supabase (run locally, once, before or after
   deploying — the deployed backend never writes to the knowledge base itself):
   ```bash
   cd backend
   # .env here needs SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and whichever
   # EMBEDDING_PROVIDER/EMBEDDING_MODEL you'll use in production — they must
   # match exactly, or query-time embeddings won't line up with these vectors.
   python ../scripts/ingest_documents.py
   python ../scripts/create_embeddings.py
   ```

### 2. Backend project (Vercel dashboard → Add New → Project → import the repo)

- **Root Directory**: `backend`
- Framework is auto-detected (Vercel recognizes `app/main.py` as a FastAPI
  entrypoint) — no build command needed.
- **Environment Variables** (Settings → Environment Variables):

  | Variable | Value |
  |---|---|
  | `SUPABASE_URL` | your project URL |
  | `SUPABASE_SERVICE_ROLE_KEY` | the `service_role` secret from step 1.3 |
  | `LLM_PROVIDER` | `anthropic` or `openai` |
  | `LLM_API_KEY` | your key |
  | `LLM_MODEL` | e.g. `claude-sonnet-5` |
  | `EMBEDDING_PROVIDER` | `openai` (needs its own `EMBEDDING_API_KEY`) or `local` |
  | `EMBEDDING_DIMENSIONS` | must match `schema.sql`'s `vector(N)` and step 1.4 |
  | `CORS_ORIGINS` | the frontend's Vercel URL (see step 3 — set this *after* the frontend is deployed, then redeploy the backend) |
  | `EMERGENCY_NUMBER` | a real local emergency number for your audience |
  | `REPORT_MAX_FILE_SIZE_MB`, `REPORT_STORAGE_BUCKET`, `OCR_LANGUAGE` | defaults are fine (`10`, `medical-reports`, `eng`) |

- Deploy, then note the resulting URL (e.g. `https://chatter-backend.vercel.app`).

> ⚠️ **OCR does not work on a standard Vercel deployment.** Scanned PDFs and
> photographed reports need the Tesseract/Poppler binaries, and Vercel's Python
> Functions have no OS package manager to install them (would require switching
> to Vercel's Docker-based Python deployment). Text-based PDF and DOCX reports
> are unaffected. Uploading a scanned file in production now returns a clear
> 503 instead of a crash.

### 3. Frontend project (import the same repo as a second project)

- **Root Directory**: `frontend`
- Framework: Vite (auto-detected)
- **Environment Variables**:

  | Variable | Value |
  |---|---|
  | `VITE_API_BASE_URL` | the backend URL from step 2, no trailing slash (e.g. `https://chatter-backend.vercel.app`) |

- Deploy, then note this URL too (e.g. `https://chatter-frontend.vercel.app`).

### 4. Close the loop

Go back to the **backend** project's env vars, set `CORS_ORIGINS` to the
frontend's URL from step 3, and redeploy the backend (env var changes need a
redeploy to take effect). Then open the frontend URL and confirm `/api/health`
via the browser network tab shows no CORS errors.

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
