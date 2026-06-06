# Session: 2026-06-04 (b)

## Type

Sprint 4 kickoff + hardening (frontend polish, upload reliability, purge path).

## Goal

- A1: GIS foundation plan only (no risky DB change)
- B1: Frontend document browser
- B2: Upload flow UX polish
- C1: Regression checks for multi-permit + citations
- Upload reliability fixes and offboarding purge path with role tiers

---

## Completed

### Sprint 4 kickoff

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
- Added frontend helper tests: `frontend/src/api.test.js`
- Added backend regressions:
  - `tests/test_query_answer_route.py`
  - `tests/test_permit_classifier.py` (multi-scope regression case)
- Fixed frontend test environment issue:
  - `frontend/src/api.js` now uses `import.meta.env?.VITE_API_BASE_URL` for Node test compatibility.

### Sprint 4 hardening

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

## Validation outcomes

- Frontend tests: pass (user confirmed)
- Backend targeted regressions: pass (user confirmed)
  - `24 passed in 0.09s`
  - `26 passed in 0.35s`

---

## Files changed

- `implementation_plan.md`, `docs/postgis_migration_checklist.md`
- `frontend/src/*` (document browser, upload UX, tests)
- `api/routes/upload.py`, `api/routes/admin.py`
- `scripts/purge_project_uploads.py`
- `tests/test_query_answer_route.py`, `tests/test_upload_route.py`, `tests/test_purge_project_uploads_script.py`
- `README.md`, `docs/api.md`, `STATE.md`
- `journals/session_260604b.md` (created)

---

## Next session should

1. Begin Task 14A PostGIS execution from approved checklist.
2. Verify extension state and API health after PostGIS enable.
3. Note ephemeral vs durable install path before Task 14B pilot load.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260604b.md`. Sprint 4 kickoff and hardening are done. Execute Task 14A PostGIS validation from `docs/task14ab_execution_checklist.md`. Confirm `postgis` + `vector` extensions and API health. Record whether PostGIS install is ephemeral or durable before Task 14B.

## Git commit message

feat(sprint4): add document browser, upload hardening, and purge governance path
