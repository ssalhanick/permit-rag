# permit_rag — State

_Updated: 2026-06-03 (post-tracing eval+guard reconfirmed PASS; frontend phase active)_

## Phase

Phase transition: API+eval hardening complete; frontend module is now active focus

## Blocked on

- None.

## Next 3 tasks

1. Add frontend document browser against `GET /documents` and `GET /documents/status`
2. Add one-click quick test auto-submit + optional per-query timing chart in UI
3. Polish frontend UX for testing speed (one-click quick-test submit + compact diagnostics view)

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend 🔧

_rag note: hybrid tuning stabilized for current phase; reranker + conflict_detector are deferred backlog items_
_api note: core + documents + admin routes live; CORS/error-shape/auth hardening complete with dedicated route/app-level tests._
_frontend note: kickoff now includes first flow + chat history + citation-linked source chunk viewer + quick-test buttons + debug panel._
_tracing note: `POST /query/answer` now captures LangSmith runs with `X-Client-Session-Id` and `X-Client-Request-Id` metadata._

## Current operational snapshot

- Ingestion pipeline health (last full check): download ✅ extraction ✅ chunking ✅ embedding ✅
- Vector DB: Postgres + pgvector (`chunks.embedding vector(768)`)
- API live routes:
  - `POST /query`, `POST /query/answer`, `GET /health`
  - `GET /documents`, `GET /documents/{doc_id}`, `GET /documents/status`
  - `PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`
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
- Governance: documents are never deleted; lifecycle is `active/superseded/repealed/needs_ocr/draft`.
- Security baseline: admin routes enforce auth by default (`API_ADMIN_AUTH_REQUIRED=true`) with token + role allowlist (`API_ADMIN_ALLOWED_ROLES`).
- Admin token policy: rotate `API_ADMIN_TOKEN` at least every 30 days and after suspected secret exposure or admin roster change.
- CORS policy: env-driven allowlist via `API_CORS_ALLOW_ORIGINS`; wildcard only via explicit dev override `API_CORS_ALLOW_ALL=true`.

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

## Validation / verification steps (canonical)

1. `py -m pytest tests/test_documents_routes.py` (latest: `12 passed`)
2. `py -m pytest tests/test_eval_guard.py` (latest: `3 passed`)
3. `py -m pytest tests/test_api_main.py` (latest: `5 passed`)
4. `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export` (latest: `ragas_20260602_214048.json`, PASS)
5. `py -m evaluation.eval_guard` (latest: PASS on `ragas_20260602_214048.json`)

For older run logs, command-by-command history, and dated deltas, use journal entries (`journals/session_260531.md` + subsequent sessions).
