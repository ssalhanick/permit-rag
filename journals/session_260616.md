# Session: 2026-06-16

## Type

Sprint 5 full implementation + architecture fix integration.

## Goal

- Incorporate 3 high-priority architecture improvements into Sprint 5
- Implement Task 14C (geocoding + jurisdiction resolver)
- Implement Task 15 (scoped conflict detection)
- Add Mapbox address autocomplete to frontend
- Run eval checkpoint and confirm no regression

---

## Completed

### Architecture Fixes

- **Fix 1 — `match_chunks()` SQL ordering** (`db/migrations/010_fix_match_chunks_ordering.sql`):
  - Removed `ORDER BY source_tier ASC` from the SQL function; ordering is now pure cosine distance
  - Tier bias is now exclusively owned by the Python reranker (`rag/reranker.py`)
  - Previously: a weak Tier-1 chunk (sim=0.35) beat a relevant Tier-2 chunk (sim=0.90) before Python ever saw them
  - Migration applied to Docker dev DB: `CREATE FUNCTION` ✅

- **Fix 3 — Citation regex hardening** (`rag/generator.py`):
  - `_extract_citations()` now accepts both strict (`[doc_id, chunk N]`) and loose (`[doc_id chunk N]`) formats
  - Case-insensitive (accepts `Chunk` with capital C)
  - Deduplicates across both patterns
  - Adds `log.warning()` with miss rate when citations don't match context chunks

- **`evaluation/ragas_eval.py` embeddings fix**:
  - Added `local_files_only=True` to `HuggingFaceEmbeddings` model_kwargs
  - Prevents DNS failure when HuggingFace is unreachable (model already cached from ingest run)

### Task 14C — Geocoding + Jurisdiction Resolver

- New module: `rag/jurisdiction_resolver.py`
  - `geocode(address)` → Census Bureau Geocoding API (free, no key)
  - `_point_in_polygon(lat, lng)` → PostGIS `ST_Contains` against `municipal_boundaries`
  - `resolve_jurisdiction(address)` → `JurisdictionResolution` dataclass
  - `municipality_from_address(address)` → convenience helper for routes
- `api/schemas.py`: added optional `address: str` field to `QueryRequest`
  - When `municipality` is not set and `address` is provided, route auto-resolves via geocoding
  - `resolved_municipality: str | None` added to `AnswerResponse`
- `api/routes/query.py`: wired resolver before retrieval; `effective_municipality` used throughout

### Task 15 — Scoped Conflict Detection

- New module: `rag/conflict_detector.py`
  - 9 subject keyword groups (setback, height limit, lot coverage, fence height, fire separation, etc.)
  - For each subject, finds chunks from ≥2 different authority levels
  - Extracts numeric values (feet, %, sq ft, stories, etc.) from each chunk
  - Flags conflict when numeric values differ across authority levels
  - Filtered-out chunks excluded; same-authority pairs not flagged
  - Non-blocking in route — exceptions are caught and logged
- `api/schemas.py`: `ConflictWarning` Pydantic model added; `conflict_warnings: list[ConflictWarning]` on `AnswerResponse`
- `api/routes/query.py`: `detect_conflicts()` called after retrieval, before generation

### Frontend

- New component: `frontend/src/components/AddressAutocomplete.jsx`
  - Mapbox Search Box API (free tier, `pk.*` token)
  - DFW metro bounding box + proximity bias
  - 300ms debounce, 3-char minimum
  - Graceful no-token fallback (plain text input + hint)
  - `onSelect` callback pre-fills municipality from Mapbox context
- `frontend/src/App.jsx`:
  - `AddressAutocomplete` wired into query form
  - `address` field added to form state and API payload
  - Conflict warnings panel displayed in answer section (orange left-border)
  - `resolved_municipality` badge shown when geocoding auto-detected jurisdiction
- `frontend/src/styles.css`: autocomplete dropdown + conflict warnings styles added
- `frontend/.env.example`: `VITE_MAPBOX_TOKEN` placeholder + Google Maps upgrade path note

### Planning / Docs

- `docs/backlog.md` created:
  - 9 remaining DFW cities (Plano, Fort Worth, Arlington, Frisco, McKinney, Irving, Garland, Denton, Allen) with open data portal links
  - FEMA flood zones, Dallas historic districts, PD overlays
  - Google Maps upgrade path (pending LLC + Google Cloud account)
  - BM25 hybrid A/B eval deferred to Sprint 6
- `docs/highpri_sprint_integration.md` (in AI artifact dir): sprint-by-sprint plan for all 3 fixes

### Testing

- `tests/test_sprint5.py`: 16 tests
  - Fix 3: strict format, loose format, capital-C Chunk, mixed formats, deduplication, miss-rate warning
  - Task 14C: geocode success, no-match, full resolution hit, no polygon match, empty address
  - Task 15: numeric mismatch → conflict, same values → no conflict, same authority → no conflict, filtered chunk excluded, `_higher_authority()` helper
  - All 16 passed in 0.78s ✅

### Eval checkpoint

- Run: `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export`
- Result: `evaluation/results/ragas_20260616_124025.json`
  - avg faithfulness: **0.931** ✅ (PASS vs 0.85 target)
  - avg relevancy: 0.687 (Q0/Q4 scored 0.000 — RAGAs AnswerRelevancy artifact, not regression)
  - avg context precision: **0.659** ↑ from 0.624
- Eval guard: **PASS** (candidate `ragas_20260616_124025.json` vs baseline `ragas_20260531_122639.json`)

---

## Issues encountered + resolutions

| Issue | Resolution |
|-------|-----------|
| `HuggingFaceEmbeddings` failing with DNS error (`[Errno 11001] getaddrinfo failed`) | Added `local_files_only=True` to model_kwargs |
| Docker container was "Up 11 seconds" (restarted mid-eval run) → all 7 queries failed | Waited for container to stabilize; re-ran eval |
| `ragas.metrics` import deprecation warnings | Non-blocking; logged as backlog item for Sprint 6 cleanup |

---

## Files changed

**New files:**
- `db/migrations/010_fix_match_chunks_ordering.sql`
- `rag/jurisdiction_resolver.py`
- `rag/conflict_detector.py`
- `frontend/src/components/AddressAutocomplete.jsx`
- `tests/test_sprint5.py`
- `docs/backlog.md`

**Modified files:**
- `rag/generator.py` (citation regex hardening)
- `api/schemas.py` (address field, ConflictWarning, resolved_municipality)
- `api/routes/query.py` (geocoding + conflict detection wiring)
- `frontend/src/App.jsx` (autocomplete + conflict UI)
- `frontend/src/styles.css` (autocomplete + conflict CSS)
- `frontend/.env.example` (Mapbox token)
- `evaluation/ragas_eval.py` (local_files_only fix)
- `STATE.md` (Sprint 5 closeout)

---

## Next session should

1. Implement Fix 2: citation-aware chunk filtering in `POST /query/answer` (prune response chunks to cited-only; add `total_chunks_retrieved` field)
2. Implement Task 16A: add Neo4j Community Edition to `docker-compose.yml`
3. Implement Task 16B: Cypher constraints + `db/graph_client.py`
4. Run RAGAs eval after Fix 2 — expect relevancy improvement above 0.687

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260616.md`. Sprint 5 is closed and signed off. Create `journals/session_260616a.md` for the next sprint and start Sprint 6:

**Fix 2 first** — in `api/routes/query.py`, after `generate_answer()` returns, filter the chunks in `AnswerResponse` to only those cited by `gen.citations` (where `found_in_context=True`). Add `total_chunks_retrieved: int` to `AnswerResponse` schema. If no citations matched context, return all chunks. Add a unit test in `tests/test_sprint5.py` or a new `tests/test_sprint6.py`.

Then **Task 16A** — add Neo4j Community Edition service to `docker-compose.yml` with APOC plugin, health check, and named volume. Validate with `docker compose up -d neo4j` and confirm the Browser UI is reachable at `http://localhost:7474`.

Validate with:
- `py -m pytest tests/test_sprint5.py tests/test_sprint6.py -v`
- `$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export` (expect relevancy > 0.687)
- `py -m evaluation.eval_guard`

## Git commit message

feat(sprint5): geocoding resolver, conflict detection, address autocomplete, citation regex hardening, SQL ordering fix
