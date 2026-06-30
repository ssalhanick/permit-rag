# permit_rag

RAG-powered construction permit compliance tool for the DFW market.
Contractors and project managers query it to get cited answers from
Dallas, Plano, Frisco, McKinney, and Fort Worth municipal codes,
plus Texas state and federal regulations.

---

## Current Status (2026-06-30)

- **Sprint 11 complete + smoke-tested** — Cognito Google SSO confirmed working locally. 93 tests passing.
- Custom JWT/Argon2id auth replaced with Cognito RS256 JWKS verification.
- Google SSO + optional TOTP 2FA supported. Vite proxy added for local dev.
- DB migration 013 applied locally: `cognito_sub` column live.
- `frontend/.env.production` created with Cognito vars for CI/CD build.
- Next: apply migration 013 to RDS, register production callback URLs, push to `deployment/sites`.

```powershell
# Full test suite
py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py tests/test_sprint9.py -v

# Apply DB migration
py scripts/run_migration.py 013_cognito_auth.sql

# Health check (API must be running)
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get

# Eval guard (no regression)
py -m evaluation.eval_guard
```

---

## TODO

### In Progress
*None*

### Planned
- [ ] [Sprint 12: User Profile Dashboard](docs/sprint12_user_profile_dashboard.md) — WordPress-style sidebar + subpages for base users (`feat/sprint-12-user-profile-dashboard`)
- [ ] [Sprint 11: Document Governance UI](docs/sprint11_document_updates.md) — metadata edit + supersede on `/documents`
- [ ] [Agent Implementation Plan](../..\.gemini\antigravity\brain\acda4bb1-53b2-4cf2-b710-5e93089c1fab/agent_implementation_plan.md) — Implement single-responsibility agents (Query Deconstructor, Semantic Conflict Analyzer, Citation Verification) with the `instructor` library and dynamic token truncation.
- [ ] [Token Optimization & Cost-Effectiveness Plan](../..\.gemini\antigravity\brain\acda4bb1-53b2-4cf2-b710-5e93089c1fab\token_optimization_plan.md) - Analyze prompt caching, chunking strategies, and embedding model trade-offs to minimize Claude token usage.
- [ ] [CMS Admin Dashboard](.gemini\antigravity\brain\acda4bb1-53b2-4cf2-b710-5e93089c1fab\cms_admin_dashboard_plan.md)

### Upcoming
- [ ] Add CI/CD pipeline to push from github to AWS
- [ ] Add ability to update existing documents
- [ ] Camera Phone (lidar Progressive Enhancement) - Use the device's camera to scan building facades and rooms to measure distances and accurately calculate square footage through the device's lidar data (or as much as doing a recording/set of pitcutres derived from the recording of the site/room)
- [ ] 3D Map Integration - Integrate with an open-source 3D map library (e.g., CesiumJS) to display the city boundaries and proposed site
- [ ] 

### Completed
- [x] Cognito Auth Migration (Sprint 11) — Replaced custom JWT/Argon2id with Amazon Cognito RS256 JWKS verification, Google SSO, optional TOTP 2FA, lazy RDS user provisioning via `GET /auth/me`
- [x] Get GIS auto-address bar working (Implemented Mapbox Search Box session_token management for address autocomplete suggestions and geocoding retrievals)
- [x] Add mobile styles (SGP10: Responsive styling for mobile, tablet, and desktop viewports, scrollable data tables, and WCAG AAA touch target size conformance)

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

Local dev uses **split env files** — see [docs/environment_setup.md](docs/environment_setup.md).

```powershell
Copy-Item .env.local.example .env.local
Copy-Item .env.example .env
Copy-Item frontend\.env.local.example frontend\.env.local
```

| File | Purpose |
|------|---------|
| `.env.local` | Docker Postgres (`localhost:5433`), CORS, Neo4j — auto-loaded locally |
| `.env` | Secrets only: `ANTHROPIC_API_KEY`, `API_JWT_SECRET`, `API_ADMIN_TOKEN` |
| `frontend/.env.local` | `VITE_MAPBOX_TOKEN` for address autocomplete |

Production (AWS/ECS) uses Terraform task env + SSM — no dotenv files in the container.

**Minimum secrets to fill in `.env`:**

| Variable | What to set |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `API_JWT_SECRET` | Random string, 32+ characters |
| `API_ADMIN_TOKEN` | Random string for `/admin/*` routes |

Database URLs are in `.env.local` (already point at Docker on port 5433).

---

### Step 3 — Start the database

```powershell
docker compose up -d
```

This starts a local Postgres 17 + pgvector + PostGIS container on **port 5433**. The schema
(`db/schema.sql`) and init SQL (`db/init/*.sql`) are applied automatically on
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
> Get-Content db/migrations/006_jurisdictions.sql      | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/migrations/007_postgis_extension.sql  | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/migrations/008_municipal_boundaries_pilot.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag
> Get-Content db/migrations/009_purge_audit_log.sql    | docker exec -i permit_rag_db psql -U postgres -d permit_rag
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

To start the entire application stack (Docker databases, FastAPI backend, and Vite frontend) with a single command on Windows, run the orchestrator script from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

To stop all services and shut down database containers:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1
```

*Alternatively, you can start individual services manually:*

```powershell
# Terminal 1 — DB (if not already running)
docker compose up -d

# Terminal 2 — API
py -m uvicorn api.main:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend
npm run dev
```

## AWS Production Deployment

The application is configured for a robust, production-grade cloud deployment on AWS utilizing infrastructure-as-code (Terraform) and automated containerized pipelines.

### Cloud Architecture Overview
*   **VPC & Networking**: Custom VPC with public subnets (hosting the ALB and S3/CloudFront entry points) and private subnets (hosting ECS Fargate container tasks).
*   **Database Tier**: Amazon RDS PostgreSQL instance running in public subnets (to facilitate direct bootstrapping/seeding) with `pgvector` and `postgis` spatial extensions enabled.
*   **API Tier**: ECS Fargate container cluster running FastAPI backend tasks behind an Application Load Balancer (ALB).
*   **Frontend Tier**: Static React SPA hosted in an Amazon S3 bucket and distributed globally via a CloudFront CDN.
*   **Security & SSL**: Traffic is fully encrypted via an ACM Wildcard SSL Certificate (`*.scottsalhanick.com`) bound to CloudFront. Runtime secrets are stored securely in AWS SSM Parameter Store as `SecureString` parameters.

---

### Deployment Prerequisites
1.  **AWS CLI**: Configured locally with administrative credentials (`aws configure`).
2.  **Docker Desktop**: Running locally to compile and build the production backend Docker container.
3.  **Terraform**: CLI installed locally (v1.5+).
4.  **SSM Parameters**: Ensure the following parameters are populated in the AWS Systems Manager Parameter Store as `SecureString` types:
    *   `/permit_rag/prod/anthropic_api_key` (Claude API key)
    *   `/permit_rag/prod/jwt_secret` (Randomly generated 32-character token signing secret)
    *   `/permit_rag/prod/admin_token` (Secure administrative access token)
    *   `/permit_rag/prod/neo4j_bolt_url` (AuraDB graph layer connection URI)
    *   `/permit_rag/prod/neo4j_auth` (Graph credentials, formatted as `neo4j/<your-auradb-password>`)

---

### Initial Setup & Re-provisioning

If you are deploying the AWS infrastructure from scratch:
```powershell
# Deploy all AWS resources
npm run deploy:infra
```

#### Database Initialization
Once Amazon RDS is provisioned, bootstrap the schema tables, custom roles, migrations, and seeds:
1. Retrieve the master database password:
   ```powershell
   terraform -chdir=terraform output -raw db_password
   ```
2. Update the `DATABASE_URL` in your local `.env` to point to the RDS endpoint.
3. Run the bootstrap script:
   ```powershell
   py scripts/init_rds_db.py
   ```
   *(Note: This script automatically drops and recreates the `public` schema on run to guarantee a clean, duplicate-error-free initialization).*

---

### Deploying Updates

Automated root-level NPM commands orchestrate building, packaging, and shipping code changes to AWS:

*   **Deploy Entire Stack**: Runs full infrastructure checks, builds and pushes the backend container to ECR (with ECS rolling restart), and compiles/syncs the frontend to S3 with CDN cache invalidation:
    ```powershell
    npm run deploy
    ```
*   **Deploy Backend Only**: Recompiles the FastAPI backend Docker image (which pre-caches the embedding model inside the container for faster start times), pushes to ECR, and triggers a rolling service update on ECS Fargate:
    ```powershell
    npm run deploy:backend
    ```
*   **Deploy Frontend Only**: Compiles the React static assets, syncs files to the S3 bucket with `--delete` to remove stale assets, and invalidates the CloudFront CDN cache:
    ```powershell
    npm run deploy:frontend
    ```

---

### Production Security & DDoS Protection (WAF & Database Routing)

#### 1. AWS WAF (Web Application Firewall) Setup
To protect your FastAPI backend from API spam and prevent runaway LLM costs (via Claude API calls on the `/query/answer` endpoint), configure a Web ACL with rate-limiting:
1. Go to the **AWS WAF & Shield** console.
2. **Important**: Change your AWS Console region filter to **Global (CloudFront)**.
3. Click **Create Web ACL** and associate it with your CloudFront distribution.
4. Add a custom **Rate-based rule**:
   *   **Rule Type**: Rate-based rule.
   *   **Rate Limit**: `300` requests per rolling 5-minute window per IP.
   *   **Action**: **Block** (returns an HTTP 403 Forbidden page to abusers).
5. Complete the setup and deploy the Web ACL.

#### 2. RDS Database Port Hardening
For initial local migrations, the database was temporarily open to public traffic. Now that bootstrapping is complete, **close the public PostgreSQL port**:
1. Remove the temporary `0.0.0.0/0` ingress block from the RDS security group in `terraform/main.tf`.
2. Apply the firewall changes:
   ```powershell
   cd terraform
   terraform apply
   ```
   *(Your backend ECS containers connect to the RDS database using VPC-internal routing rules, so they do not require public port ingress to function).*

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

## Docs Table of Contents

Project docs in `docs/`:

| File | Purpose |
|---|---|
| `docs/api.md` | API endpoint usage, auth headers, and runtime config notes |
| `docs/offboarding_runbook.md` | User offboarding purge procedure (single + bulk) and verification |
| `docs/postgis_migration_checklist.md` | Sprint 4 GIS/PostGIS rollout checklist (planning-only gates) |
| `docs/task14ab_execution_checklist.md` | Step-by-step execution/rollback checklist for Task 14A/14B |
| `docs/sprint4_qa_checklist.md` | Frontend + citation regression QA checklist and sign-off flow |

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

# Create an API Token
py -c "import secrets; print(secrets.token_urlsafe(32))"

# Purge one uploaded project document (requires admin token/role)
py -m scripts.purge_project_uploads --doc-id "<doc_id>" --admin-role owner

# Purge many docs listed in a text file (one doc_id per line)
py -m scripts.purge_project_uploads --doc-id-file "docs_to_purge.txt" --admin-role owner
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

# Admin purge action (deletes chunks/vectors + local raw file, keeps repealed tombstone row)
curl -s -X POST http://localhost:8000/admin/documents/project-doc-1/purge-project-upload \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: owner"
```

Admin runtime security/env flags:
- `API_ADMIN_AUTH_REQUIRED=true|false` (default `true`)
- `API_ADMIN_TOKEN=<secret>`
- `API_ADMIN_ALLOWED_ROLES=admin,owner` (default `admin`)
- `API_PURGE_ANY_TIER_ROLES=owner` (roles allowed to purge non-project tiers)
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
