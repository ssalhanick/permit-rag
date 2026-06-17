# permit_rag — State

_Updated: 2026-06-16b (Sprint 7 close)_

## Phase

Sprint 7 is closed. Task 16D (graph_health in /health) and Task 16E (cross-authority Cypher traversal + graph-backed conflict detector) are live. 60 tests passing.

## Blocked on

- **Mapbox token**: `VITE_MAPBOX_TOKEN` not yet set in `frontend/.env` — address autocomplete degrades gracefully to plain text input until token is added. See `frontend/.env.example`.

## Next 3 tasks

1. Sprint 8 — Live validation: `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` (expect `graph_health=True`)
2. Sprint 8 — Task 16F (optional): enrich graph with query signals — tag cited chunks as graph nodes after each `/query/answer` call
3. Sprint 8 — BM25 A/B eval: measure hybrid vs dense-only retrieval quality delta

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend ✅ graph ✅

_db note: Sprint 1 migrations applied — `content_hash` + `status` on chunks, `source_tier` on documents, `match_chunks()` updated. **Sprint 5 migration 010**: `match_chunks()` ORDER BY fixed — pure cosine ordering, tier bias now owned exclusively by Python reranker. Roles `corpus_writer`/`app_reader` live on Docker dev DB._
_rag note: multi-permit classifier live (`rag/permit_classifier.py`). **Sprint 5**: `conflict_detector.py` implemented (lightweight numeric cross-authority conflict detection). `jurisdiction_resolver.py` implemented (Census geocoding + PostGIS ST_Contains). Citation regex hardened (strict + loose format, miss-rate warning). **Sprint 7 Task 16E**: `detect_conflicts_with_graph()` added — optional graph-backed path using Neo4j Cypher traversal; falls back to lightweight detector when Neo4j is unreachable._
_api note: `POST /query/answer` returns `ahj_disclaimer` + `permit_types` + **`conflict_warnings`** + **`resolved_municipality`** + **`total_chunks_retrieved`**. **Sprint 6 Fix 2**: `chunks` array now contains only citation-filtered chunks (`found_in_context=True`); falls back to all chunks when no citations match context. Optional **`address`** field on `QueryRequest` auto-resolves municipality via geocoding. **Sprint 7 Task 16D**: `GET /health` now returns `graph_health: bool` (Neo4j ping, additive — does not affect overall `status`)._
_frontend note: query flow + document browser + upload UX live. **Sprint 5**: `AddressAutocomplete` component added (Mapbox Search API, DFW-bbox restricted, degrades gracefully without token). Conflict warnings panel added to answer view._
_tracing note: `POST /query/answer` captures LangSmith runs with `X-Client-Session-Id` and `X-Client-Request-Id` metadata._
_graph note: **Task 16A** — Neo4j CE in `docker-compose.yml`. **Task 16B** — `db/graph_client.py` singleton Bolt driver + helpers. **Task 16C** — `scripts/sync_graph.py` bulk-sync. **Task 16D** — `graph_health` field in `GET /health`. **Task 16E** — `find_cross_authority_conflicts()` Cypher traversal; `detect_conflicts_with_graph()` in `rag/conflict_detector.py`._

## Current operational snapshot

- Ingestion pipeline health (last full check): download ✅ extraction ✅ chunking ✅ embedding ✅
- Vector DB: Postgres + pgvector (`chunks.embedding vector(768)`), PostGIS now baked into local DB image build path
- Schema additions (Sprint 1): `chunks.content_hash`, `chunks.status`, `documents.source_tier`
- DB roles: `corpus_writer` (ingestion writes), `app_reader` (API reads + query_log insert)
- API live routes:
  - `POST /query`, `POST /query/answer` (+ `ahj_disclaimer`), `GET /health`
  - `GET /documents`, `GET /documents/{doc_id}`, `GET /documents/status`
  - `PATCH /admin/documents/{doc_id}`, `POST /admin/documents/{doc_id}/supersede`, `POST /admin/documents/{doc_id}/purge-project-upload`
- Docs: `README.md` + `docs/api.md` reflect current API surface.

## Quality gates (current)

- Latest full eval: `evaluation/results/ragas_20260616_143411.json` _(Sprint 6 checkpoint)_
  - avg faithfulness `0.910` ✅ (PASS vs `0.85` target)
  - avg relevancy `0.689` ✅ (> 0.687 Sprint 5 baseline; Q0/Q4 at 0.000 = RAGAs cosine-collapse artifact)
  - avg context precision `0.654`
  - q1 faithfulness `0.875` (above baseline `0.600`)
- Eval guard: PASS (candidate `ragas_20260616_143411.json` vs baseline `ragas_20260531_122639.json`)
- Answer cache policy for eval: keep `RAGAS_ANSWER_CACHE_ENABLED=false`
- Metric delta vs Sprint 5 (`ragas_20260616_124025.json`):
  - avg faithfulness: `-0.021` (`0.931 → 0.910`, still well above gate)
  - avg relevancy: `+0.002` (`0.687 → 0.689`, marginal improvement — Fix 2 filters at API layer, eval harness bypasses route)
  - avg context precision: `-0.005` (`0.659 → 0.654`, within noise)

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
- Purge audit validation decision: do **not** restore `mansfieldtx-tx-2` now; it was used only to verify tier-2 audit logging and is not present in active catalog/registry scope.
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
- [x] Task 14A durability: replaced ephemeral PostGIS install with durable Docker build/image approach (`db/Dockerfile`, `docker-compose.yml`, `db/init/01_extensions.sql`)
- [x] Task 14B pilot: loaded first municipal boundary layer and validated geometry + point-in-polygon
- [x] Purge audit logging path added (`db/migrations/009_purge_audit_log.sql`, `db/client.py`, `api/routes/admin.py`, script header support)
- [x] Sprint 4 closeout docs/sign-off sweep completed (`STATE.md`, `docs/sprint4_qa_checklist.md`, `README.md`)
- [x] Restore decision recorded for audit-validation purge doc (`mansfieldtx-tx-2`): no restore required at this time

### Sprint 5 — Geocoding + Conflict Detection + Architecture Fixes (2026-06-16)
- [x] Fix 1: `match_chunks()` SQL ORDER BY corrected — pure cosine ordering, tier bias moved to Python reranker only (`db/migrations/010_fix_match_chunks_ordering.sql`, `db/schema.sql`)
- [x] Fix 3: Citation regex hardened — accepts both `[doc_id, chunk N]` (strict) and `[doc_id chunk N]` (loose/capital-C) formats; unmatched citations now log miss-rate warning (`rag/generator.py`)
- [x] Task 14C: `rag/jurisdiction_resolver.py` — Census Bureau geocoding API + PostGIS `ST_Contains` point-in-polygon; `municipality_from_address()` convenience helper
- [x] Task 14C: Optional `address` field added to `QueryRequest` — auto-resolves municipality via geocoding when `municipality` not explicitly set; `resolved_municipality` returned on `AnswerResponse`
- [x] Task 15 (scoped): `rag/conflict_detector.py` — lightweight numeric discrepancy detection across 9 permit subject keywords; cross-authority-level pairs only; non-blocking in route
- [x] Task 15: `ConflictWarning` Pydantic model added to `api/schemas.py`; `conflict_warnings: list[ConflictWarning]` on `AnswerResponse`; wired into `api/routes/query.py`
- [x] Frontend: `AddressAutocomplete` component (`frontend/src/components/AddressAutocomplete.jsx`) — Mapbox Search API, DFW bbox, 300ms debounce, graceful no-token fallback
- [x] Frontend: Conflict warnings panel added to answer view; `resolved_municipality` detection badge; autocomplete + conflict CSS added to `styles.css`
- [x] Backlog: `docs/backlog.md` created — 9 DFW city boundaries pending, FEMA/historic overlays, Google Maps upgrade path, BM25 A/B eval
- [x] `frontend/.env.example` updated with `VITE_MAPBOX_TOKEN` placeholder
- [x] `evaluation/ragas_eval.py` fixed: `local_files_only=True` in `HuggingFaceEmbeddings` prevents DNS failure when HuggingFace is unreachable
- [x] Sprint 5 tests: `tests/test_sprint5.py` — 16 tests covering Fix 3 citation variants, jurisdiction resolver (mocked), conflict detector (5 cases)
- [x] Eval checkpoint: faithfulness `0.931` ✅, context precision `0.659` ↑, no regression vs Sprint 4 baseline

### Sprint 6 — Graph Layer + Architecture Fix 2 (2026-06-16a)
- [x] Fix 2: citation-aware chunk filtering in `POST /query/answer` — `chunks` array trimmed to cited-only (`found_in_context=True`); fallback to all chunks when no citations match context; `total_chunks_retrieved: int` added to `AnswerResponse` (`api/schemas.py`, `api/routes/query.py`)
- [x] Task 16A: Neo4j Community Edition added to `docker-compose.yml` — `neo4j:5-community`, APOC enabled via `NEO4J_PLUGINS`, ports 7474+7687, `neo4jdata` named volume, health check
- [x] `.env.example` updated with `NEO4J_AUTH` + `NEO4J_BOLT_URL` placeholders
- [x] Sprint 6 tests: `tests/test_sprint6.py` — 8 tests covering citation filter logic, fallback, dedup, schema field presence
- [x] Eval run: faithfulness `0.910` ✅ | relevancy `0.689` ✅ | guard PASS (`ragas_20260616_143411.json`)
- [x] Task 16B: `db/graph_client.py` — singleton Bolt driver, `upsert_document_node`, `upsert_chunk_node`, `link_supersession`, `apply_constraints`, `ping`, read helpers
- [x] `db/cypher/constraints.cypher` — 5 UNIQUE constraints + 4 indexes, idempotent (IF NOT EXISTS)
- [x] `neo4j` pip package installed; `tests/test_sprint6.py` expanded to 19 tests (35 total with sprint5) ✅
- [x] Task 16B bootstrap: constraints applied to live Neo4j container ✅
- [x] Task 16C: `scripts/sync_graph.py` — bulk-sync Postgres corpus → Neo4j; dry-run, municipality + doc-id filters, SUPERSEDED_BY edge linking
### Sprint 7 — Graph Health + Graph Conflict Detection (2026-06-16b)
- [x] Task 16D: `graph_health: bool` field added to `HealthResponse` schema (`api/schemas.py`) — defaults `False`, non-load-bearing
- [x] Task 16D: `health_check()` in `api/main.py` calls `_graph_client.ping()` non-blocking; `graph_health` returned in response; overall `status` driven by Postgres only
- [x] Task 16E: `find_cross_authority_conflicts(subject_keyword)` added to `db/graph_client.py` — Cypher traversal matching Document pairs via `GOVERNED_BY` to different `AuthorityLevel` nodes; returns Chunk content for numeric comparison; never raises (returns `[]` on error)
- [x] Task 16E: `_graph_pairs_to_conflicts()` + `detect_conflicts_with_graph()` added to `rag/conflict_detector.py` — graph-backed Tier B path; falls back to lightweight Tier A when Neo4j unreachable or empty
- [x] Sprint 7 tests: `tests/test_sprint7.py` — 20 tests (8 Task 16D + 12 Task 16E) → **60 total** ✅

## Validation / verification steps (canonical)

1. `py -m pytest tests/test_governance.py tests/test_permit_classifier.py -v 2>&1` (latest: `35 passed`)
2. `py -m pytest tests/test_documents_routes.py` (latest: `12 passed`)
3. `py -m pytest tests/test_eval_guard.py` (latest: `3 passed`)
4. `py -m pytest tests/test_api_main.py` (latest: `5 passed`)
5. `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export` (latest: Sprint 5 checkpoint `ragas_20260616_124025.json`, faithfulness `0.931` PASS)
6. `py -m evaluation.eval_guard` (latest: run against Sprint 5 checkpoint)
11b. `py -m pytest tests/test_sprint5.py -v` (latest: `16 passed in 0.78s`)
7. `cd frontend; npm run test` (latest: pass after `import.meta.env` Node-safe fallback)
8. `py -m pytest tests/test_query_answer_route.py tests/test_permit_classifier.py -v` (latest user-reported: `24 passed` then `26 passed` across targeted runs)
9. `py -m pytest tests/test_upload_route.py -v` (latest: pass after upload reliability fixes)
10. `py -m pytest tests/test_documents_routes.py tests/test_purge_project_uploads_script.py -v` (latest: pass after purge tier controls)
11. `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` (latest: `healthy`, `database=True` after enabling PostGIS)
12. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT extname FROM pg_extension WHERE extname IN ('postgis','vector') ORDER BY extname;"` (latest: both extensions present)
13. `py -m pytest tests/test_documents_routes.py tests/test_purge_project_uploads_script.py -v` (latest user-reported: `19 passed`)
14. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT jurisdiction_id, ST_SRID(geom) AS srid, GeometryType(geom) AS geom_type, ST_IsValid(geom) AS is_valid FROM municipal_boundaries;"` (latest: `dallas | 4326 | MULTIPOLYGON | t`)
15. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT indexname FROM pg_indexes WHERE tablename='municipal_boundaries' ORDER BY indexname;"` (latest includes GiST geom + jurisdiction indexes)
16. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT jurisdiction_id FROM municipal_boundaries WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(-96.7970, 32.7767), 4326));"` (latest: `dallas`)
17. `Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get` (latest: `healthy`, `database=True`)
18. `Invoke-RestMethod -Uri "http://localhost:8000/query" -Method Post -ContentType "application/json" -Body '{"query":"What are building permit requirements in Dallas?","top_k":5,"municipality":"dallas"}'` (latest: `num_results=5`, `top_similarity=0.8020`)
19. `Get-Content db/migrations/009_purge_audit_log.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag` (latest: `CREATE TABLE`, `CREATE INDEX`, `CREATE INDEX`)
20. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT id, doc_id, actor_identity, actor_role, source_tier, created_at FROM purge_audit_log ORDER BY created_at DESC LIMIT 5;"` (latest: table query succeeds, `0 rows` before first purge event)
21. `docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT doc_id, actor_identity, actor_role, source_tier, deleted_chunk_count, local_file_deleted, created_at FROM purge_audit_log ORDER BY created_at DESC LIMIT 5;"` (latest: audit row present for `mansfieldtx-tx-2`, role `owner`, tier `2`, deleted chunks `88`)
22. `rg "mansfieldtx-tx-2|mansfieldtx-tx-1" documents/catalog.json documents/registry.json` (latest: no matches; restore not required for active corpus scope)

For older run logs, command-by-command history, and dated deltas, use journal entries (`journals/session_260531.md` through `journals/session_260604d.md`; latest: `session_260604d.md`).
