# Sprint 4 QA Checklist

Date: 2026-06-04  
Scope: frontend polish + multi-permit citation regression

## 0) Preflight

- [x ] API is up on `http://localhost:8000`
- [ x] Frontend is up on `http://localhost:5173`
- [ x] Browser cache cleared or hard refresh done
- [ x] `.env` values loaded for API auth/CORS

## 1) Route Smoke Check

- [ x] Open `/` and confirm query page loads
- [x ] Open `/documents` and confirm document browser loads
- [ x] Open `/upload` and confirm upload form loads
- [x ] Nav links switch pages with no console errors

## 2) Document Browser QA (`/documents`)

### Basic load

- [ x] Page shows filters, status summary, and documents table
- [ x] Loading state appears briefly on first load
- [x ] No error banner on healthy API

### Filters

- [x ] Enter `municipality=dallas` and confirm row set updates
- [x ] Enter `status=active` and confirm row set narrows
- [x ] Enter `authority=municipal` and confirm row set narrows
- [ x] Enter `doc_type=building_code` and confirm row set narrows
- [x ] Click **Clear filters** and confirm filters reset + results repopulate

### Status summary

- Bucket = one status group from `/documents/status` response.
- Example: `active: 19` means one bucket (`status=active`, `count=19`).
- [x ] Status chips render for returned buckets
- [ ] Bucket counts match API response totals
- [ ] Empty-state message shows when no status buckets
- [ ] Empty-state test: set `status=repealed` (or other missing status) and confirm "No status data..." appears

### Table integrity

- [x ] Columns show: doc_id, municipality, doc_type, authority, status, updated_at
- [x ] No duplicated row keys visible in console
- [x ] Long content does not break layout (horizontal scroll works)

## 3) Upload Flow QA (`/upload`)

### Readiness blockers

- [ x] With empty form, checklist shows required blockers
- [x ] Add file only: blockers reduce correctly
- [x ] Add `doc_id`, `municipality`, token: checklist reaches **Ready to upload** where do i get the auth token?

### File handling

- [x ] Upload accepts `.pdf`
- [x ] Upload accepts `.html` / `.htm`
- [x ] File name auto-suggests `doc_id` slug when `doc_id` empty
- [x ] Manual `doc_id` edit still allowed after auto-suggest

### Error guidance

- [ x] Bad token shows auth-friendly message
- [ ] Bad file type shows file-type guidance
- [ ] API down shows network/CORS guidance

### Success flow

- [x ] Success card shows `doc_id`, `status`, `local_path`
- [x ] Poll link to `/documents/{doc_id}` opens and works
- [ x] **Upload another** resets form and messages

## 4) Query/Citation Regression QA (`/`)

Primary query:
- `garage conversion with electrical rewire and new bathroom plumbing` 

Expected:
- [ ] `permit_types` includes `building`, `electrical`, `plumbing`
- [ ] At least one citation in answer payload
- [ ] Citation list renders clickable items
- [ ] Citation click opens matching source chunk in viewer
- [ ] No empty `doc_id` or invalid `chunk_index` in citations

If guardrail blocks with low confidence (422):
- [x ] Record `top_similarity` and message in this checklist
- [- ] Retry with fallback query 1: `What are the fire sprinkler requirements for new construction in Dallas?`
- [ x] Retry with fallback query 2: `What are the building permit requirements in Plano?`
- [x ] Confirm at least one fallback query returns citations in UI

Actual notes:
- `garage conversion with electrical rewire and new bathroom plumbing`: Insufficient retrieval confidence for grounded answer. `chunks=5`, `top_similarity=0.6760`, required `top_similarity>=0.74`
- `What are the fire sprinkler requirements for new construction in Dallas`: Insufficient retrieval confidence for grounded answer. chunks=5, top_similarity=0.7110, required_chunks>=3, required_top_similarity>=0.74

## 4B) Targeted eval notes after GIS pilot (Task 14B)

- [x] Record boundary load result (`municipal_boundaries` row count)
- [x] Record point-in-polygon result for Dallas sample point
- [ ] Re-run one Dallas retrieval query and record top similarity
- [ ] Note whether GIS pilot changed retrieval behavior (expected: no change in current phase)

Notes:
- 2026-06-04: Durable PostGIS Docker build path landed and validated.
- 2026-06-04 Task 14B SQL outputs:
  - Extensions: `postgis`, `vector`
  - Geometry check: `dallas | 4326 | MULTIPOLYGON | t`
  - Spatial indexes present: `idx_municipal_boundaries_geom`, `idx_municipal_boundaries_jurisdiction`
  - Point-in-polygon sample (`-96.7970, 32.7767`) resolved to `dallas`

## 5) Fast Command Checks

Run frontend tests:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag\frontend"; npm run test`

Run backend regressions:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; py -m pytest tests/test_query_answer_route.py tests/test_permit_classifier.py -v`

## 6) Sign-off

- [x ] QA pass complete
- [ ] Bugs captured (if any) with repro steps
    - when importing a new document, the chunking seems to time out and the embedding doesn't work
- [ ] `STATE.md` updated if scope or blockers changed
