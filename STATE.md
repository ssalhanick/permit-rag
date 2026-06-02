# permit_rag — State

_Updated: 2026-06-02 (API hardening verified; latest eval/guard reconfirmed PASS)_

## Phase

Week 2 of 9 (calendar) — Evaluation active (Phase 4 deliverables pulled forward)

## Blocked on

- None.

## Next 3 tasks

1. Write session closeout notes in today’s journal with pass/fail/pass variance pattern and final PASS candidate
2. Prepare commit + next-session prompt (frontend scaffold planning)
3. Keep periodic eval checks to monitor run variability around faithfulness gate

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend ⏳

_rag note: hybrid tuning stabilized for current phase; reranker + conflict_detector are deferred backlog items_
_api note: core + documents + admin routes live; CORS/error-shape/auth hardening complete with dedicated route/app-level tests._

## Current operational snapshot

- Ingestion pipeline health (last full check): download ✅ extraction ✅ chunking ✅ embedding ✅
- Vector DB: Postgres + pgvector (`chunks.embedding vector(768)`)
- API live routes:
  - `POST /query`, `POST /query/answer`, `GET /health`
  - `GET /documents`, `GET /documents/{doc_id}`, `GET /documents/status`
  - `PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`
- Docs: `README.md` + `docs/api.md` reflect current API surface.

## Quality gates (current)

- Latest full eval: `evaluation/results/ragas_20260602_151539.json`
  - avg faithfulness `0.899` (PASS vs `0.85`)
  - avg relevancy `0.826`
  - avg context precision `0.583`
  - q1 faithfulness `0.933` (above baseline `0.600`)
- Eval guard: PASS (candidate `ragas_20260602_151539.json`) against baseline `ragas_20260531_122639.json`
- Answer cache policy for eval: keep `RAGAS_ANSWER_CACHE_ENABLED=false`
- Dated run-by-run metrics/deltas (including pass/fail/pass variability on 2026-06-02) live in journals

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

## Validation / verification steps (canonical)

1. `py -m pytest tests/test_documents_routes.py` (latest: `12 passed`)
2. `py -m pytest tests/test_eval_guard.py` (latest: `3 passed`)
3. `py -m pytest tests/test_api_main.py` (latest: `5 passed`)
4. `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
5. `py -m evaluation.eval_guard`

For older run logs, command-by-command history, and dated deltas, use journal entries (`journals/session_260531.md` + subsequent sessions).
