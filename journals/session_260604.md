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

## Next session should

1. Review and approve PostGIS go/no-go checklist before any DB extension/image change.
2. Run targeted multi-permit eval notes (beyond unit tests) and capture citation-grounding drift.
3. Add purge audit log trail (`who`, `role`, `doc_id`, `source_tier`, timestamp) and tests.

## Prompt for next session

Read `AGENTS.md`, `STATE.md`, and `journals/session_260604.md`. Sprint 4 hardening is complete for upload reliability, purge role tiers, and frontend QA. Next: run/record a focused multi-permit eval pass with citation-grounding observations, then add purge audit logging. Do not run risky PostGIS DB changes until checklist gates are explicitly approved.

## Git commit message

feat(admin+upload): harden upload flow and add tiered purge tooling/docs

