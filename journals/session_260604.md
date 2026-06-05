# Session: 2026-06-04

## Type

Feature completion + test stabilization (Sprint 3 closeout).

## Goal

Finish Sprint 3 tasks:
- Task 9: document change detection + supersession flow
- Task 11: multi-permit classifier

## Completed

- Implemented/validated document-level change detection flow in `ingestion/governance.py`:
  - hash compare (`NO_CHANGE`, `NEW_DOCUMENT`, `CHANGED`)
  - supersession path for changed docs
  - optional rechunk/re-embed trigger path
- Validated DB helper usage for governance in `db/client.py`:
  - `get_document_by_doc_id`
  - `supersede_document`
  - `delete_chunks_for_document`
- Implemented classifier module in `rag/permit_classifier.py`:
  - permit type mapping + keyword fallback
  - integration path used by query flow
- Wired permit detection into API response path:
  - `api/routes/query.py` now calls classifier
  - `api/schemas.py` includes `permit_types`
- Fixed test import-target issue by adding `db/__init__.py` so local package patching resolves correctly.

## Validation outcomes

- `py -m pytest tests/test_governance.py tests/test_permit_classifier.py -v 2>&1` -> `35 passed`
- `py -m pytest -v 2>&1` -> `35 passed`

## Current status

- Sprint 3 complete and stable.
- Branch pushed by user.
- `STATE.md` updated for Sprint 3 completion and next tasks.

## Sprint 4 kickoff addendum (same day)

### Scope handled

- A1: GIS foundation plan only (no risky DB change)
- B1: Frontend document browser
- B2: Upload flow UX polish
- C1: Regression checks for multi-permit + citations

### Completed in this addendum

- Added planning docs:
  - `implementation_plan.md`
  - `docs/postgis_migration_checklist.md`
- Added frontend document browser route:
  - `frontend/src/DocumentBrowserPage.jsx`
  - `frontend/src/main.jsx` (`/documents`)
  - `frontend/src/Nav.jsx` (`Documents` link)
  - `frontend/src/api.js` (`fetchDocuments`, `fetchDocumentStatus`)
  - `frontend/src/styles.css` (browser table/filter styles)
- Polished upload UX:
  - `frontend/src/UploadPage.jsx` (readiness blockers, status banners, clearer errors)
  - `frontend/src/uploadUtils.js` (helper functions)
  - `frontend/src/uploadUtils.test.js` (new tests)
- Added frontend helper tests:
  - `frontend/src/api.test.js`
- Added backend regressions:
  - `tests/test_query_answer_route.py`
  - `tests/test_permit_classifier.py` (multi-scope regression case)
- Fixed frontend test environment issue:
  - `frontend/src/api.js` now uses `import.meta.env?.VITE_API_BASE_URL` for Node test compatibility.

### Validation outcomes (addendum)

- Frontend tests: pass (user confirmed)
- Backend targeted regressions: pass (user confirmed)
  - `24 passed in 0.09s`
  - `26 passed in 0.35s`

## Sprint 4 hardening addendum (later same day)

### Scope handled

- Upload reliability fixes for PDF/HTML background processing
- QA checklist clarification and completion pass
- Offboarding purge path (chunks/vectors/raw file purge) with role tiers
- Reusable purge script with env token loading
- Docs updates (`README.md`, `docs/api.md`, `STATE.md`)

### Completed in this addendum

- Fixed upload background processing order:
  - chunk by `doc_id` -> insert chunks -> embed -> activate
  - file: `api/routes/upload.py`
- Added HTML-specific resilience:
  - retry chunking once with procedural filter disabled when first pass yields zero chunks
  - failure status split: PDF -> `needs_ocr`, HTML -> `draft`
  - tests: `tests/test_upload_route.py`
- Added admin purge endpoint:
  - `POST /admin/documents/{doc_id}/purge-project-upload`
  - deletes chunks (and vectors), deletes local raw file under `documents/raw`, tombstones metadata
  - file: `api/routes/admin.py`
- Added purge role tiering:
  - normal admin can purge project uploads (`source_tier=3`)
  - elevated role (`API_PURGE_ANY_TIER_ROLES`) can purge any source tier
- Added reusable script:
  - `scripts/purge_project_uploads.py`
  - supports `--doc-id` and `--doc-id-file`
  - auto-loads `API_ADMIN_TOKEN` from `.env` via `load_dotenv()`
  - tests: `tests/test_purge_project_uploads_script.py`
- Added docs TOC in README for files under `docs/`.

## Sprint 4 GIS execution addendum (late same day)

### Scope handled

- Began Task 14A execution from approved PostGIS checklist
- Verified extension state and API health after PostGIS enable

### Completed in this addendum

- Confirmed baseline issue:
  - `vector` extension present, `postgis` missing on default `pgvector/pgvector:pg17` container
- Enabled PostGIS in running dev container and validated:
  - `SELECT extname ...` returned both `postgis` and `vector`
  - API health check returned `healthy`, `database=True`
- Created Task 14A/B execution checklist:
  - `docs/task14ab_execution_checklist.md`

### Important note

- Current PostGIS enablement is ephemeral (installed in running container).
- Next session must make this durable via Docker build/image path before Task 14B pilot data load.

## Next session should

1. Make Task 14A durable via Docker image/build update (PostGIS + pgvector together after rebuild).
2. Execute Task 14B pilot boundary load and run geometry/index/point-in-polygon checks.
3. Add purge audit log trail (`who`, `role`, `doc_id`, `source_tier`, timestamp) and tests.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260604.md`. Task 14A extension validation passed (`postgis` + `vector` active and API healthy), but PostGIS install is currently ephemeral in-container. First, make PostGIS durable via Docker image/build path. Then execute Task 14B pilot boundary load with geometry and point-in-polygon validation. After GIS pilot, continue purge audit logging and targeted eval notes.

## Git commit message

chore(gis): validate task14a postgis extensions and record durable-next steps

## Sprint 4 durability + audit addendum (same session)

### Scope handled

- Made Task 14A durable in Docker image/build path
- Staged Task 14B pilot boundary migration + validation commands
- Added purge audit log trail (`who`, `role`, `doc_id`, `source_tier`, timestamp)

### Completed in this addendum

- Added durable DB image:
  - `db/Dockerfile` now installs `postgresql-17-postgis-3` packages on top of `pgvector/pgvector:pg17`
  - `docker-compose.yml` now builds local DB image from `db/Dockerfile`
  - `db/init/01_extensions.sql` added (`postgis`, `vector`, `pgcrypto`)
- Added GIS pilot migrations:
  - `db/migrations/007_postgis_extension.sql`
  - `db/migrations/008_municipal_boundaries_pilot.sql` (pilot Dallas envelope multipolygon, SRID 4326, GiST index)
- Added purge audit logging:
  - `db/migrations/009_purge_audit_log.sql`
  - `db/client.py` -> `insert_purge_audit_log()`
  - `api/routes/admin.py` purge route now records audit row with `X-Admin-User` + `X-Admin-Role`
  - `scripts/purge_project_uploads.py` supports `--admin-user` and sends `X-Admin-User`
- Updated docs:
  - `docs/task14ab_execution_checklist.md` (Task 14B command block + validation queries)
  - `docs/offboarding_runbook.md` (`X-Admin-User` usage)
  - `README.md` startup/migration notes updated for PostGIS-inclusive stack
- Added/updated tests:
  - `tests/test_documents_routes.py`
  - `tests/test_purge_project_uploads_script.py`
  - `tests/test_db_client_purge_audit.py` (new)

### Validation outcomes (addendum)

- User-reported:
  - `docker compose up -d --build` -> DB image built and container started
  - `py -m pytest tests/test_documents_routes.py tests/test_purge_project_uploads_script.py -q` -> `19 passed in 8.16s`
  - Task 14B SQL checks:
    - extensions: `postgis`, `vector`
    - geometry validation: `dallas | 4326 | MULTIPOLYGON | t`
    - indexes on `municipal_boundaries`: `idx_municipal_boundaries_geom`, `idx_municipal_boundaries_jurisdiction` (+ PK/unique)
    - point-in-polygon sample check returned `dallas`

### Next session should

1. Run API smoke after DB rebuild (`/health` + one retrieval query) and record output in checklist.
2. Add targeted eval notes tied to GIS pilot outcomes (top similarity + behavior delta note).
3. Verify `purge_audit_log` row insertion from one purge call.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260604.md`. Task 14A durability is now landed via Docker build path, and purge audit logging code is in place. Run Task 14B pilot boundary migration commands, capture geometry/index/point-in-polygon outputs, then finish targeted eval notes and finalize checklist/state updates.

## Git commit message

feat(gis): make postgis durable and add purge audit trail
