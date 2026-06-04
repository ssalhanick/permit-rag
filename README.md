# permit_rag

RAG-powered construction permit compliance tool for the DFW market.
Contractors and project managers query it to get cited answers from
Dallas, Plano, Frisco, McKinney, and Fort Worth municipal codes,
plus Texas state and federal regulations.

---

## Timeline

| Week | Dates | Phase | Deliverables | Status |
|------|-------|-------|-------------|--------|
| 1 | May 19–25 | Foundation | Project scaffold, Docker + pgvector, harvester (13 docs), chunker + verification, embedder (nomic-embed-text-v1.5), 10 docs ingested, 7,170 chunks embedded | ✅ Done |
| 2 | May 26–Jun 1 | Retrieval | `rag/pipeline.py` — dense retrieval + feature-flagged hybrid (dense+BM25 RRF), retrieval quality testing with contractor queries | 🔶 Active |
| 3 | Jun 2–8 | Generation + API | `rag/generator.py` — Claude-powered answer generation with citations, `api/` — FastAPI endpoints for query + document management | |
| 4 | Jun 9–15 | Evaluation | `evaluation/` — RAGAs integration (faithfulness, relevancy, precision, recall), build evaluation dataset (30–50 hand-written Q&A pairs) | |
| 5 | Jun 16–22 | Tuning | Chunk size ablation (500–3000 chars), overlap ablation (0–400), top_k ablation (3–10), hybrid search experiment (HNSW + BM25 RRF) | |
| 6 | Jun 23–29 | Frontend | `frontend/` — Vite + React chat UI, source citation display, document browser | |
| 7 | Jun 30–Jul 6 | Audit + Governance | `audit/` — query logging, `ingestion/governance.py` — document lifecycle, supersession, freshness monitoring | |
| 8 | Jul 7–13 | Integration | End-to-end testing, conflict detection, multi-municipality queries, edge case hardening | |
| 9 | Jul 14–20 | Production Prep | Deployment config (Supabase or RDS), environment separation, CI/CD, load testing | |
| 10 | Jul 21–Aug 1 | Polish + Demo | Documentation, demo recording, pitch deck, final RAGAs scores, code cleanup | |

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- Node.js 18+ and npm (for the frontend)

---

### Step 1 — Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -e ".[dev]"
pip install sentence-transformers einops   # local embedding model
```

---

### Step 2 — Environment variables

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in at minimum:

| Variable | What to set |
|---|---|
| `DATABASE_URL` | `postgresql://postgres:<your-password>@localhost:5433/permit_rag` |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `CORPUS_WRITER_URL` | `postgresql://corpus_writer:changeme_rotate_corpus@localhost:5433/permit_rag` |
| `APP_READER_URL` | `postgresql://app_reader:changeme_rotate_reader@localhost:5433/permit_rag` |

All other variables have working defaults for local dev.

---

### Step 3 — Start the database

```powershell
docker compose up -d
```

This starts a local Postgres 17 + pgvector container on **port 5433**. The schema
(`db/schema.sql`) and roles (`db/init/02_roles.sql`) are applied automatically on
first boot.

Verify it is running:

```powershell
docker ps   # should show permit_rag_db as Up
```

> **If the volume already exists** and you want to apply new migrations manually:
> ```powershell
> Get-Content db/migrations/002_chunk_content_hash.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/migrations/003_chunk_status.sql       | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/migrations/004_source_tier.sql        | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/migrations/005_match_chunks_update.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/init/02_roles.sql                     | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> ```

---

### Step 4 — (First time only) Ingest documents

Skip this if the DB already has data (`chunks` table is populated).

```powershell
# Download source documents
py -m ingestion.harvester harvest

# Chunk + insert into DB
py -m scripts.ingest_documents

# Embed all chunks locally (takes a few minutes — runs nomic-embed-text-v1.5)
py -m ingestion.embedder
```

---

### Step 5 — Start the API

```powershell
py -m uvicorn api.main:app --reload --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

### Step 6 — Start the frontend

Open a **second terminal** (keep the API running in the first):

```powershell
cd frontend
npm install       # first time only
npm run dev
```

Open the URL Vite prints — usually `http://localhost:5173`.

Current frontend routes:
- `/` — query flow with answer, citations, source chunk viewer, and debug logs
- `/documents` — document browser with filters and status summary
- `/upload` — admin upload flow with readiness checks and error guidance

---

### Everyday startup (after first-time setup)

```powershell
# Terminal 1 — DB (if not already running)
docker compose up -d

# Terminal 2 — API
py -m uvicorn api.main:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend
npm run dev
```

---

## LangChain MCP Adapters (Optional)

`langchain-mcp-adapters` is an optional integration layer that lets LangChain
agents call tools exposed by MCP (Model Context Protocol) servers. In this
project, it is intended for future tool-based workflows and is not required
for core ingestion/retrieval/generation paths.

### Why use it

- Connect LangChain flows to MCP tool servers without custom transport code
- Reuse MCP tool definitions in local or remote agent workflows
- Keep MCP integrations isolated from core app dependencies

### Install / activate

If `langchain-mcp-adapters` is configured as an optional dependency group
(e.g., `mcp`) in `pyproject.toml`:

```bash
# from project root, with venv active
pip install -e ".[mcp]"
```

---

## Project Structure

```
permit_rag/
├── ingestion/          # Document harvesting, chunking, verification
│   ├── harvester.py    # Download + tag municipal documents
│   ├── chunker.py      # PDF/HTML extraction + text splitting
│   ├── verification.py # Stage-by-stage ingestion verification
│   ├── embedder.py     # nomic-embed-text-v1.5 local embedding (768-dim)
│   └── governance.py   # Document lifecycle management
├── db/
│   ├── schema.sql      # Postgres + pgvector schema (4 tables)
│   └── client.py       # psycopg3 connection pool + CRUD helpers
├── rag/                # Retrieval + generation pipeline (active)
├── api/                # FastAPI endpoints (query + documents + admin + health)
├── docs/               # Supplemental docs (API usage examples)
├── evaluation/         # RAGAs evaluation workflows (active)
├── audit/              # Query audit logging (scaffold)
├── frontend/           # Vite + React UI (query + documents + upload)
├── documents/
│   ├── raw/            # Downloaded PDFs + HTML (gitignored)
│   ├── metadata/       # JSON sidecar per document
│   ├── catalog.json    # Source catalog entries for harvester
│   └── registry.json   # Master document registry
├── scripts/            # One-off utilities
├── tests/              # pytest test suite
├── journals/           # Session logs
├── docker-compose.yml  # Postgres + pgvector (pg17)
├── pyproject.toml      # Dependencies + tool config
└── STATE.md            # Current project state
```

---

## Commands

```bash
# Start local Postgres + pgvector (port 5433)
docker compose up -d

# Download all catalog documents
# If a matching doc_id file already exists in documents/raw and --force is not set,
# harvester reuses the local raw file instead of downloading from URL.
py -m ingestion.harvester harvest

# Force re-download even if unchanged
py -m ingestion.harvester harvest --force

# Check all sources for changes (run weekly)
py -m ingestion.harvester monitor

# Print governance summary
py -m ingestion.harvester report

# Edit source entries for harvesting
# (add/remove docs and metadata here)
# documents/catalog.json

# Ingest all passing documents into DB (chunk + insert)
py -m scripts.ingest_documents

# Re-ingest existing doc_ids too (use after normalization changes)
py -m scripts.ingest_documents --include-existing

# Embed a single document (smoke test)
py -m ingestion.embedder texas-contractor-licensing-electrical

# Embed all documents
py -m ingestion.embedder

# Force re-embed all chunks (including already-embedded chunks)
py -m ingestion.embedder --force

# Chunk + verify all documents (no DB insert)
py -m scripts.run_chunk_verify
```

---

## API Quick Start

```bash
# Run API locally
py -m uvicorn api.main:app --reload --port 8000
```

Interactive docs:
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

Documented endpoint examples also live in `docs/api.md`.

### API examples

```bash
# Health check
curl -s http://localhost:8000/health

# Retrieval query
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"What are the setback requirements for a residential fence in Dallas?\",\"top_k\":5,\"municipality\":\"dallas\"}"

# List/filter documents
curl -s "http://localhost:8000/documents?municipality=dallas&status=active&authority=municipal&doc_type=building_code"

# Document detail
curl -s http://localhost:8000/documents/dallas-building-code

# Status aggregation for current filter scope
curl -s "http://localhost:8000/documents/status?municipality=dallas&authority=municipal"

# Admin metadata patch (set API_ADMIN_TOKEN in env to enforce header auth)
curl -s -X PATCH http://localhost:8000/admin/documents/dallas-building-code \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: admin" \
  -d "{\"document_status\":\"draft\",\"retrieval_weight\":0.55}"

# Admin supersession action
curl -s -X POST http://localhost:8000/admin/documents/dallas-building-code-2024/supersede \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: admin" \
  -d "{\"replacement_doc_id\":\"dallas-building-code-2026\",\"superseded_weight\":0.1}"
```

Admin runtime security/env flags:
- `API_ADMIN_AUTH_REQUIRED=true|false` (default `true`)
- `API_ADMIN_TOKEN=<secret>`
- `API_ADMIN_ALLOWED_ROLES=admin,owner` (default `admin`)
- Admin token policy: rotate `API_ADMIN_TOKEN` every 30 days and on any suspected secret exposure or admin roster change.

CORS/env flags:
- `API_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:5173`
- `API_CORS_ALLOW_ALL=true` (dev-only wildcard override)

API errors (including validation) are normalized as:
- `{"detail": "<string>"}`

---

## Document Ingestion Pipeline

Use this workflow for deterministic ingestion with normalization and embedding refresh.

### 1) Set normalization + retrieval controls in `.env`

```bash
CHUNK_NORMALIZATION_ENABLED=true
CHUNK_PROCEDURAL_FILTER_ENABLED=true
CHUNK_PROCEDURAL_DROP_THRESHOLD=3
CHUNK_FILTER_WARN_DROP_RATIO=0.50
RETRIEVAL_PROCEDURAL_PENALTY_ENABLED=true
RETRIEVAL_PROCEDURAL_PENALTY=0.015
RETRIEVAL_PROCEDURAL_MAX_HITS=4
RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED=true
RETRIEVAL_NON_MUNI_MUNICIPAL_PENALTY=0.06
RETRIEVAL_NON_MUNI_SCOPE_MATCH_BONUS=0.02
RETRIEVAL_NON_MUNI_SCOPE_MISMATCH_PENALTY=0.03
# Hybrid retrieval rollout (default off for safe fallback)
RETRIEVAL_HYBRID_ENABLED=false
RETRIEVAL_DENSE_TOP_N=20
RETRIEVAL_BM25_TOP_N=20
RETRIEVAL_RRF_K=60
RETRIEVAL_RRF_DENSE_WEIGHT=1.0
RETRIEVAL_RRF_BM25_WEIGHT=1.0
```

### 2) Download/update sources

```bash
# Reuse local raw files when doc_id files already exist
py -m ingestion.harvester harvest
```

### 3) Ingest to DB

```bash
# New docs only (default)
py -m scripts.ingest_documents

# Include existing docs (recommended after cleaning/normalization changes)
py -m scripts.ingest_documents --include-existing
```

### 4) Embed vectors

```bash
# Standard embed (only chunks with NULL embeddings)
py -m ingestion.embedder

# Force re-embed all chunks (use after major text normalization updates)
py -m ingestion.embedder --force
```

### 5) Validate ingestion quality

```bash
# Retrieval previews for weak queries
py -m rag.pipeline --municipality dallas --top-k 10 "What are the setback requirements for a residential fence in Dallas?"
py -m rag.pipeline --top-k 10 "What are the ADA accessibility requirements for commercial buildings?"
py -m rag.pipeline --municipality plano --top-k 10 "What are the building permit requirements in Plano?"
py -m rag.pipeline --municipality dallas --top-k 10 "What are the fire sprinkler requirements for new construction in Dallas?"

# Focused RAGAs pass then full suite
$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --query 0 1 2 3 5 --export
$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export

# Regression guard against confirmatory baseline (fails on metric drift)
py -m evaluation.eval_guard --candidate evaluation/results/ragas_20260601_010352.json

# Hybrid retrieval validation (feature-flagged)
$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m rag.pipeline --municipality dallas --top-k 10 "What are the setback requirements for a residential fence in Dallas?"
$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m rag.pipeline --municipality dallas --top-k 10 "What are the fire sprinkler requirements for new construction in Dallas?"
$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --query 0 1 2 3 5 --export
$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export
```

Notes:
- `chunk_document()` logs normalization stats (`chunks_before_filter`, `chunks_dropped`, `chunk_drop_ratio`).
- If `chunk_drop_ratio` exceeds `CHUNK_FILTER_WARN_DROP_RATIO`, review source quality and thresholds.
- Hybrid mode is rollback-safe: set `RETRIEVAL_HYBRID_ENABLED=false` to return to dense-only retrieval immediately.
- As of 2026-05-31 latest full run (`ragas_20260531_102544.json`), hybrid faithfulness is `0.852` (gate pass), but q1 remains unstable; keep `RETRIEVAL_HYBRID_ENABLED=false` by default until one more confirmatory full run.
- `evaluation.eval_guard` defaults to baseline `evaluation/results/ragas_20260531_122639.json` and fails if avg faithfulness drops below `0.85` or q1 faithfulness drops by more than `0.10`.
- Keep `STATE.md` as a compact current snapshot; store dated metric timelines and per-run deltas in `journals/` session logs.

RAGAs metric definitions used in this repo:
- **Faithfulness**: How well the answer is supported by retrieved context (higher = less hallucination).
- **Relevancy**: How directly the answer addresses the user query.
- **Context precision**: How much of the retrieved context is actually useful/relevant to the query.
- **Top similarity (`top_sim`)**: Similarity score of the highest-ranked retrieved chunk for that query.

---

## Ingestion Health Check

Use this quick checklist after catalog or harvesting changes:

```bash
# Validate catalog loader and duplicate/required-field checks
py -m pytest tests/test_harvester_catalog.py

# Rebuild registry from current catalog/raw state
py -m ingestion.harvester harvest

# Compare catalog vs registry coverage and list missing doc_ids
py -m ingestion.harvester report

# Ingest to DB and refresh vectors
py -m scripts.ingest_documents --include-existing
py -m ingestion.embedder --force
```

Expected health indicators:
- Harvester summary prints `Used local raw` and `Downloaded from URL` counts.
- `report` shows `Catalog documents`, `Registry documents`, and `Missing from registry`.
- Missing list should only contain intentionally non-harvestable/manual-only sources.

---

## Chunking Strategy

Documents are split using **recursive character splitting**
([LangChain RecursiveCharacterTextSplitter](https://python.langchain.com/docs/modules/data_connection/document_transformers/recursive_text_splitter/)),
tuned for legal/code text.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Chunk size | 1,500 chars | ~375 tokens for nomic-embed-text-v1.5 (8K context). Holds a complete code section. |
| Overlap | 200 chars | Prevents splitting mid-sentence at boundaries. |
| Split hierarchy | Section → paragraph → line → sentence → clause → word | Prefers clean breaks between legal sections. |

### Split hierarchy (tried in order)

1. `\n\n\n` — section breaks
2. `\n\n` — paragraph breaks
3. `\n` — line breaks
4. `. ` — sentence ends
5. `; ` — clause breaks
6. `, ` — comma breaks
7. ` ` — word breaks

### Optimization plan

Chunk size and overlap will be empirically tuned in Week 4–5 via
ablation study using [RAGAs](https://docs.ragas.io/) metrics:

- Grid search: chunk_size ∈ {500, 1000, 1500, 2000, 3000},
  overlap ∈ {0, 100, 200, 400}, top_k ∈ {3, 5, 10}
- Metrics: context precision, context recall, faithfulness,
  answer relevancy
- Evaluation set: ~30–50 hand-written questions with known
  ground-truth answers from ingested documents

### Pipeline

```
Raw file (PDF/HTML)
  → Text extraction (pypdf / BeautifulSoup)
  → Clean text (normalize whitespace, strip boilerplate)
  → Recursive split (1500 chars, 200 overlap)
  → Verification (coverage ≥ 80%, ≥ 1 chunk)
  → Chunks ready for embedding
```

---

## Metadata Schema

Every document in the registry carries full governance metadata:

```json
{
  "doc_id": "city-of-dallas-ordiance-v1",
  "source_url": "https://codelibrary.amlegal.com/...",
  "municipality": "dallas",
  "authority_level": "municipal",
  "doc_type": "zoning_ordinance",
  "subject_tags": ["zoning", "land-use", "setbacks"],
  "document_status": "active",
  "is_current": true,
  "retrieval_weight": 1.0,
  "review_due": "2026-07-21",
  "checksum_sha256": "a3f9...",
  "ingested_at": "2026-05-22T22:16:04Z"
}
```

---

## Document Governance

- Documents are **never deleted** — only superseded or repealed
- Superseded docs get `retrieval_weight: 0.1` (deprioritized, not removed)
- Scanned PDFs are flagged as `needs_ocr`, not silently ingested
- Verification runs at every ingestion stage — no silent failures
- Source URL changes are flagged for human review

```python
from ingestion.harvester import mark_superseded

mark_superseded(
    old_doc_id="dallas-zoning-ord-2022-11",
    new_doc_id="dallas-zoning-ord-2024-03"
)
```

---

## Architecture Decisions

- **Local Postgres 17 + pgvector** for dev; Supabase or RDS for production
- **psycopg3** (direct driver) over Supabase SDK — no vendor lock-in
- **Docker Compose** for local Postgres (pgvector/pgvector:pg17 image, port 5433)
- **FastAPI** over Flask (async support, auto OpenAPI docs)
- **Vite + React** over Next.js (simpler for MVP)
- **Claude API** for generation; **nomic-embed-text-v1.5** for embeddings (768-dim, local inference)
- **Hybrid search implemented (feature flag)**: dense (pgvector HNSW) + BM25 (tsvector + GIN) with RRF fusion, defaulted off pending faithfulness/regression gate
- **Citations** must reference publisher + date, never imply direct city authority
