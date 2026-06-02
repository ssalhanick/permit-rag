# permit_rag — State

_Updated: 2026-06-02 (compacted for context efficiency; dated history moved to journals)_

## Phase

Week 2 of 9 (calendar) — Evaluation active (Phase 4 deliverables pulled forward)

## Blocked on

- None.

## Next 3 tasks

1. Harden API for demo readiness (CORS restrictions, error shape consistency, docs refresh)
2. Add auth/RBAC strategy for admin routes beyond optional shared token
3. Address psycopg pool shutdown warnings seen after eval runs

## Module status

ingestion ✅ db ✅ rag ✅ api 🔶 eval ✅ frontend ⏳

_rag note: hybrid tuning stabilized for current phase; reranker + conflict_detector are deferred backlog items_
_api note: POST /query + GET /health + GET /documents + GET /documents/{doc_id} + GET /documents/status + PATCH /admin/documents/{doc_id} + POST /admin/documents/{doc_id}/supersede live; hardening still ⏳_

## Current operational snapshot

- Ingestion pipeline health (last full check): download ✅ extraction ✅ chunking ✅ embedding ✅
- Vector DB: Postgres + pgvector (`chunks.embedding vector(768)`)
- API live routes:
  - `POST /query`, `POST /query/answer`, `GET /health`
  - `GET /documents`, `GET /documents/{doc_id}`, `GET /documents/status`
  - `PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`
- Docs: `README.md` + `docs/api.md` reflect current API surface.

## Quality gates (current)

- Latest full eval: `evaluation/results/ragas_20260601_120058.json`
  - avg faithfulness `0.889` (PASS vs `0.85`)
  - avg relevancy `0.838`
  - avg context precision `0.620`
  - q1 faithfulness `0.765` (above baseline `0.600`)
- Eval guard: PASS (`py -m evaluation.eval_guard`) against baseline `ragas_20260531_122639.json`
- Answer cache policy for eval: keep `RAGAS_ANSWER_CACHE_ENABLED=false`
- Dated run-by-run metrics/deltas live in journals (latest: `journals/session_260531.md` addenda)

## Docs status

- 13 active · 0 superseded · 0 overdue (last harvest summary: 2026-05-22)
- 10 docs ingested · 7,170 chunks · 7,170 embeddings

## Active decisions (high-signal only)

- Dev vector stack: Dockerized Postgres + pgvector; prod target remains Supabase/RDS Postgres.
- Retrieval: hybrid dense+BM25 is enabled by default, with env toggle for rollback.
- Guardrail policy: eval gate requires avg faithfulness >= `0.85`; q1 regression guard enforced by `evaluation/eval_guard.py`.
- API architecture: FastAPI with lifespan startup/shutdown, typed schemas, and dedicated admin governance routes.
- Governance: documents are never deleted; lifecycle is `active/superseded/repealed/needs_ocr/draft`.
- Security note: admin routes currently use optional shared header token (`API_ADMIN_TOKEN`) and need stronger auth/RBAC.
- Production TODO: tighten CORS from wildcard to env-driven allowlist.

## Deliverables checklist (current phase)

- [x] Implemented document read routes (`/documents`, `/documents/{doc_id}`, `/documents/status`)
- [x] Implemented admin governance routes (`PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`)
- [x] Added tests for route behavior and validation (`tests/test_documents_routes.py`)
- [x] Added eval regression guard + tests (`evaluation/eval_guard.py`, `tests/test_eval_guard.py`)
- [x] Re-validated post-admin API quality (`ragas_20260601_120058.json`, guard PASS)
- [ ] Tighten CORS and normalize error responses for demo readiness
- [ ] Replace optional admin token with stronger auth/RBAC approach
- [ ] Resolve psycopg pool shutdown warnings after evaluation runs

## Validation / verification steps (canonical)

1. `py -m pytest tests/test_documents_routes.py` (latest: `10 passed`)
2. `py -m pytest tests/test_eval_guard.py` (latest: `3 passed`)
3. `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
4. `py -m evaluation.eval_guard`

For older run logs, command-by-command history, and dated deltas, use journal entries (`journals/session_260531.md` + subsequent sessions).
