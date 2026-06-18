# Sprint 4 Implementation Plan

## Goal

Sprint 4 starts with low-risk work:
- GIS foundation plan only (no DB migration run yet)
- Frontend polish for document browser and upload UX
- Multi-permit + citation regression checks

## Execution Order

1. A1: PostGIS migration checklist document (planning only)
2. B1: Frontend document browser page and route wiring
3. B2: Upload flow UX pass
4. C1: Regression tests for multi-permit answers and citations
5. Session closeout docs (`STATE.md`, `journals/session_YYYY-MM-DD.md`)

## A1 — GIS Foundation Plan (Checklist Only)

Deliverable files:
- `docs/postgis_migration_checklist.md`

Guardrails:
- No SQL migration added yet
- No image swap executed yet
- No extension enable command executed yet
- No production-impact command executed yet

Exit criteria:
- Checklist includes preflight, dry-run, rollback, and validation items
- Checklist includes explicit "stop/go" gate before any DB change

## B1 — Frontend Document Browser

Planned file changes:
- `frontend/src/DocumentBrowserPage.jsx` (new)
- `frontend/src/main.jsx` (route)
- `frontend/src/Nav.jsx` (nav link)
- `frontend/src/api.js` (document/status fetch helpers)
- `frontend/src/styles.css` (browser styles)

Exit criteria:
- User can load documents list
- User can view status counts
- Error and loading states are visible

## B2 — Upload UX Polish

Planned file changes:
- `frontend/src/UploadPage.jsx`
- `frontend/src/styles.css`

Exit criteria:
- Better submit-state guidance
- Clear error text and success follow-up actions
- No regression to current upload behavior

## C1 — Regression Checks (Multi-Permit + Citations)

Planned file changes:
- `tests/test_permit_classifier.py` (targeted additions)
- `tests/test_query_answer_route.py` (new route-level checks)

Exit criteria:
- Permit type list remains stable for multi-scope prompts
- Citation payload remains present and structured

## Paste Commands (when ready to run)

`py -m pytest tests/test_permit_classifier.py -v`

`py -m pytest tests/test_query_answer_route.py -v`

`py -m pytest tests/test_permit_classifier.py tests/test_query_answer_route.py -v`
