# permit_rag — State

_Updated: 2026-06-04 (Sprint 4 hardening complete + Task 14A extension validation passed)_

## Phase

Sprint 4 hardening mostly complete. GIS planning/checklist done, frontend QA pass done, upload/purge governance path added. Task 14A extension validation passed (`postgis` + `vector` present), but current PostGIS install is not yet durable across container rebuild.

## Blocked on

- None.

## Next 3 tasks

1. Make Task 14A durable: move from in-container package install to Docker image build path
2. Execute Task 14B pilot boundary load and validate geometry/index/query checks
3. Add purge audit log trail (`who`, `role`, `doc_id`, `source_tier`, timestamp)

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend ✅

_db note: Sprint 1 migrations applied — `content_hash` + `status` on chunks, `source_tier` on documents, `match_chunks()` updated (chunk status filter + tier ordering + new return cols). Roles `corpus_writer`/`app_reader` live on Docker dev DB._
_rag note: multi-permit classifier is live (`rag/permit_classifier.py`) and wired into `POST /query/answer`; conflict detector remains backlog._
_api note: `POST /query/answer` returns `ahj_disclaimer` + `permit_types`. Upload flow now chunks/inserts/embeds reliably and retries HTML chunking without procedural filter when first-pass chunks are empty. New admin purge route supports project uploads and elevated-role any-tier purge._
_frontend note: query flow + document browser route (`/documents`) + upload UX blockers/status guidance are now in place. API helper tests and upload utility tests added under `frontend/src/*.test.js`._
_tracing note: `POST /query/answer` now captures LangSmith runs with `X-Client-Session-Id` and `X-Client-Request-Id` metadata._

## Current operational snapshot

- Ingestion pipeline health (last full check): download ✅ extraction ✅ chunking ✅ embedding ✅
- Vector DB: Postgres + pgvector (`chunks.embedding vector(768)`), plus PostGIS extension enabled in current dev container
- Schema additions (Sprint 1): `chunks.content_hash`, `chunks.status`, `documents.source_tier`
- DB roles: `corpus_writer` (ingestion writes), `app_reader` (API reads + query_log insert)
- API live routes:
  - `POST /query`, `POST /query/answer` (+ `ahj_disclaimer`), `GET /health`
  - `GET /documents`, `GET /documents/{doc_id}`, `GET /documents/status`
  - `PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`, `POST /admin/documents/{doc_id}/purge-project-upload`
- Docs: `README.md` + `docs/api.md` reflect current API surface.

## Quality gates (current)

- Latest full eval: `evaluation/results/ragas_20260602_214048.json`
  - avg faithfulness `0.893` (PASS vs `0.85`)
  - avg relevancy `0.694`
  - avg context precision `0.624`
  - q1 faithfulness `0.882` (above baseline `0.600`)
- Eval guard: PASS (candidate `ragas_20260602_214048.json`) against baseline `ragas_20260531_122639.json`
- Answer cache policy for eval: keep `RAGAS_ANSWER_CACHE_ENABLED=false`
- Dated run-by-run metrics/deltas (including pass/fail/pass variability on 2026-06-02) live in journals
- Metric delta vs prior PASS (`ragas_20260602_151539.json`):
  - avg faithfulness: `-0.006` (`0.899 -> 0.893`, still PASS)
  - avg relevancy: `-0.132` (`0.826 -> 0.694`)
  - avg context precision: `+0.041` (`0.583 -> 0.624`)
  - q1 faithfulness: `-0.051` (`0.933 -> 0.882`, still above baseline)

## Docs status

- 13 active · 0 superseded · 0 overdue (last harvest summary: 2026-05-22)
- 10 docs ingested · 7,170 chunks · 7,170 embeddings

## Active decisions (high-signal only)

- Dev vector stack: Dockerized Postgres + pgvector; prod target remains Supabase/RDS Postgres.
- Retrieval: hybrid dense+BM25 is enabled by default, with env toggle for rollback.
- Guardrail policy: eval gate requires avg faithfulness >= `0.85`; q1 regression guard enforced by `evaluation/eval_guard.py`.
- API architecture: FastAPI with lifespan startup/shutdown, typed schemas, and dedicated admin governance routes.
- Governance: documents are never deleted; lifecycle is `active/superseded/repealed/needs_ocr/draft`. Chunks now have independent `status` lifecycle.
- Security baseline: admin routes enforce auth by default (`API_ADMIN_AUTH_REQUIRED=true`) with token + role allowlist (`API_ADMIN_ALLOWED_ROLES`).
- Purge tier policy: `source_tier=3` purge available to normal admin role; non-project tiers require elevated role in `API_PURGE_ANY_TIER_ROLES`.
- DB role policy: ingestion connects via `CORPUS_WRITER_URL`; API reads via `APP_READER_URL`. Rotate passwords before any shared deployment. Supabase migration: replace with service_role / anon RLS pattern (see `db/init/02_roles.sql` comments).
- Admin token policy: rotate `API_ADMIN_TOKEN` at least every 30 days and after suspected secret exposure or admin roster change.
- CORS policy: env-driven allowlist via `API_CORS_ALLOW_ORIGINS`; wildcard only via explicit dev override `API_CORS_ALLOW_ALL=true`.
- AHJ disclaimer: static URL dict in `api/routes/query.py` is a placeholder — replaced by `jurisdictions` table lookup in Sprint 2 (Task 7).

## Deliverables checklist (current phase)

- [x] Implemented document read routes (`/documents`, `/documents/{doc_id}`, `/documents/status`)
- [x] Implemented admin governance routes (`PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`)
- [x] Added tests for route behavior and validation (`tests/test_documents_routes.py`)
- [x] Added eval regression guard + tests (`evaluation/eval_guard.py`, `tests/test_eval_guard.py`)
- [x] Re-validated post-admin API quality (`ragas_20260601_120058.json`, guard PASS)
- [x] Tightened CORS to env-driven config and normalized API error payload shape
- [x] Replaced optional admin token behavior with enforced admin auth mode (token + role allowlist)
- [x] Resolved eval-time pool shutdown warnings by explicitly closing DB pool in eval CLI
- [x] Recovered eval gate to avg faithfulness >= `0.85` and passing `evaluation.eval_guard` (`ragas_20260602_141821.json`)
- [x] Added dedicated app-level tests for CORS env parsing + global error handler response format (`tests/test_api_main.py`)
- [x] Documented admin token rotation/auth policy in `README.md` and `docs/api.md`
- [x] Started frontend module with Vite + React scaffold and first interaction flow (`frontend/`)
- [x] Added frontend chat history and citation-linked source chunk viewer
- [x] Added seven quick-test question buttons for repeatable manual testing
- [x] Added frontend debug panel (health probe + request log + clearer network/CORS error hints)
- [x] Added API-level LangSmith tracing for `/query/answer` with session/request IDs

### Sprint 1 — Schema Hardening (2026-06-03)
- [x] Task 1: `AHJDisclaimer` model + `ahj_disclaimer` field on `POST /query/answer` (text + learn_more_url per municipality)
- [x] Task 2: `chunks.content_hash` column + index (migration 002)
- [x] Task 3: `chunks.status` column + index (migration 003) — chunk-level lifecycle independent of document status
- [x] Task 4: `corpus_writer` + `app_reader` Postgres roles on Docker dev DB (`db/init/02_roles.sql`); `CORPUS_WRITER_URL` + `APP_READER_URL` in `.env.example`
- [x] Task 5: `documents.source_tier` column + index (migration 004); `insert_document` + `insert_chunks` updated; `match_chunks()` updated (migration 005: chunk status filter, tier ordering, new return cols)

### Sprint 2 — Jurisdictions + Reranker (completed)
- [x] Jurisdictions table + seed added (`db/migrations/006_jurisdictions.sql`, `db/seeds/jurisdictions.sql`)
- [x] Query route updated to use jurisdiction-aware disclaimer URL pathing
- [x] Provenance/reranker updates landed (`rag/reranker.py`, retrieval wiring)

### Sprint 3 — Change Detection + Classifier (2026-06-04)
- [x] Task 9: Document-level change detection and supersession flow implemented (`ingestion/governance.py`)
- [x] Task 9: DB helpers validated for supersession/chunk lifecycle paths (`db/client.py`)
- [x] Task 11: Multi-permit classifier implemented and wired (`rag/permit_classifier.py`, `api/routes/query.py`, `api/schemas.py`)
- [x] Added/ran tests: `tests/test_governance.py`, `tests/test_permit_classifier.py` (latest combined: `35 passed`)

### Sprint 4 — Kickoff (2026-06-04)
- [x] Task A1: Added GIS migration planning artifacts only (no risky DB change): `implementation_plan.md`, `docs/postgis_migration_checklist.md`
- [x] Task B1: Added frontend document browser route and API helpers (`frontend/src/DocumentBrowserPage.jsx`, `frontend/src/api.js`, `frontend/src/main.jsx`, `frontend/src/Nav.jsx`, `frontend/src/styles.css`)
- [x] Task B2: Polished upload flow UX with readiness blockers/status feedback and error mapping (`frontend/src/UploadPage.jsx`, `frontend/src/uploadUtils.js`)
- [x] Task B1/B2 tests: `frontend/src/api.test.js`, `frontend/src/uploadUtils.test.js`
- [x] Task C1: Added multi-permit + citation regression tests (`tests/test_query_answer_route.py`, `tests/test_permit_classifier.py`)
- [x] Upload reliability hardening: fixed background upload chunk/insert/embed order; added HTML retry path and PDF-vs-HTML failure status handling (`api/routes/upload.py`, `tests/test_upload_route.py`)
- [x] Offboarding purge path: added purge endpoint + reusable script (`api/routes/admin.py`, `scripts/purge_project_uploads.py`) with role-tier controls (`API_PURGE_ANY_TIER_ROLES`)
- [x] Frontend/manual QA pass completed with checklist updates (`docs/sprint4_qa_checklist.md`)
- [x] Task 14A extension validation: confirmed `postgis` and `vector` extensions active; API `/health` recovered to healthy
- [ ] Task 14A durability: replace ephemeral in-container PostGIS package install with durable Docker build/image approach
- [ ] Task 14B pilot: load first municipal boundary layer and run geometry + point-in-polygon validation

## Validation / verification steps (canonical)

1. `py -m pytest tests/test_governance.py tests/test_permit_classifier.py -v 2>&1` (latest: `35 passed`)
2. `py -m pytest tests/test_documents_routes.py` (latest: `12 passed`)
3. `py -m pytest tests/test_eval_guard.py` (latest: `3 passed`)
4. `py -m pytest tests/test_api_main.py` (latest: `5 passed`)
5. `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export` (latest: `ragas_20260602_214048.json`, PASS)
6. `py -m evaluation.eval_guard` (latest: PASS on `ragas_20260602_214048.json`)
7. `cd frontend; npm run test` (latest: pass after `import.meta.env` Node-safe fallback)
8. `py -m pytest tests/test_query_answer_route.py tests/test_permit_classifier.py -v` (latest user-reported: `24 passed` then `26 passed` across targeted runs)
9. `py -m pytest tests/test_upload_route.py -v` (latest: pass after upload reliability fixes)
10. `py -m pytest tests/test_documents_routes.py tests/test_purge_project_uploads_script.py -v` (latest: pass after purge tier controls)
11. `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` (latest: `healthy`, `database=True` after enabling PostGIS)
12. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT extname FROM pg_extension WHERE extname IN ('postgis','vector') ORDER BY extname;"` (latest: both extensions present)

For older run logs, command-by-command history, and dated deltas, use journal entries (`journals/session_260531.md` + subsequent sessions).
