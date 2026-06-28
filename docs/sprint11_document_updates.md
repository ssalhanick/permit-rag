# Sprint 11 — Document Governance UI

**Branch:** `feat/sprint-11`  
**Status:** In progress

## Goal

Expose existing admin governance API on the Document Browser (`/documents`) so operators can update metadata and supersede documents without curl.

## Scope

| In scope | Out of scope |
|----------|--------------|
| PATCH metadata via UI | Re-ingest / replace PDF |
| Supersede flow | Edit `subject_tags`, `doc_type`, `municipality` |
| `X-Admin-Token` auth (same as Upload) | JWT-based admin |
| Fix broken purge API call in frontend | CMS dashboard |
| Frontend unit tests for admin utils | Backend schema changes |

## Editable fields (matches `DocumentAdminUpdateRequest`)

| Field | Type | Notes |
|-------|------|-------|
| `document_status` | enum | active, superseded, repealed, needs_ocr, draft |
| `is_current` | boolean | Retrieval eligibility flag |
| `retrieval_weight` | float 0–1 | Downweight superseded docs |
| `review_due` | date | Governance review date |

Supersede (`POST /admin/documents/{doc_id}/supersede`):

| Field | Default |
|-------|---------|
| `replacement_doc_id` | required |
| `superseded_weight` | 0.1 |

## Auth model

- Headers: `X-Admin-Token` (required), `X-Admin-Role: admin`
- Token stored in `sessionStorage` key `permit_rag_admin_token` (shared with Upload page)
- Signed-in user required to see admin UI; token required to submit

## API routes (existing — no backend changes)

- `GET /documents/{doc_id}` — detail for panel
- `PATCH /admin/documents/{doc_id}` — metadata update
- `POST /admin/documents/{doc_id}/supersede` — supersession
- `POST /admin/documents/{doc_id}/purge-project-upload` — purge (Profile page fix)

## Files

| File | Change |
|------|--------|
| `frontend/src/documentAdminUtils.js` | Payload builders, admin headers, session token |
| `frontend/src/api.js` | Admin fetch/update/supersede/purge helpers |
| `frontend/src/components/DocumentAdminPanel.jsx` | Edit + supersede panel |
| `frontend/src/DocumentBrowserPage.jsx` | Admin token + Edit action |
| `frontend/src/UploadPage.jsx` | Persist admin token to sessionStorage |
| `frontend/src/ProfilePage.jsx` | Pass admin token to purge |

## Verification checklist

- [ ] `/documents` → Edit → change `review_due` → Save → table refreshes
- [ ] Supersede doc A with doc B → status `superseded`, weight reduced
- [ ] Wrong admin token → clear 403 message
- [ ] Profile purge works with stored admin token
- [ ] `cd frontend && npm run test`
- [ ] `py -m pytest tests/test_documents_routes.py -v`

## Governance rules

- Documents are never hard-deleted via this UI (supersede/repeal only)
- Superseded documents must not be sole source of an answer (retrieval weight + status)
