# On-Demand URL Pull — Admin Page Harvest

**Status:** Planned
**Depends on:** existing harvester, governance, upload pipeline, admin auth

## Goal

Give the developer an admin panel with a URL input and a **Pull** button.
On click, the backend fetches the page, discovers linked files
(PDF / DOCX / PPTX / HTML / TXT / MD), and ingests only what changed.
Runs only when called — no watching, no scheduling.

Per-file decision:

- New file → ingest (chunk + embed).
- Same file, unchanged content → skip.
- Same file, changed content → ingest new version, supersede old.

## Identity model (decided)

A document's identity is resolved in this order. First hit wins.

1. **Normalized source URL** — exact match on `source_url_normalized`.
2. **Fallback** — match on `municipality + doc_type + source_filename`
   (normalized filename). Match here sets a `url_changed` review flag.
3. **No match** — brand new document.

Then checksum decides the action:

| URL/fallback match? | Checksum match? | Meaning | Action |
|---|---|---|---|
| yes | yes | unchanged | skip |
| yes | no | edited in place | new version + supersede old |
| no (fallback hit) | no | likely moved/renamed | new version + supersede old + flag `url_changed` |
| no | no | new file | ingest as new |
| no | yes (bytes seen elsewhere) | duplicate at new URL | flag for human review, do not auto-supersede |

**Rule: never supersede before the new version fully chunks + embeds.**
If extraction or embedding fails, the current active document stays active.

## Normalization (single shared function)

New module `ingestion/url_normalize.py` — one function used by **both**
the harvester and the pull route. Store the normalized value; never
normalize ad hoc at query time.

`normalize_source_url(url: str) -> str`:

- lowercase scheme + host
- force `https` compare (keep original in `source_url`)
- strip fragment (`#...`)
- strip tracking params (`utm_*`, `gclid`, `fbclid`, `mc_*`)
- resolve relative → absolute against the page URL
- collapse duplicate slashes, normalize trailing slash

`normalize_filename(name: str) -> str`:

- lowercase, strip query/extension noise
- strip version/date suffixes (`-v2`, `(1)`, `-2024-03`, ` copy`)
- keep base name for fallback identity

Both get unit tests (`tests/test_url_normalize.py`).

## Schema migration — `db/migrations/022_source_identity.sql`

Add identity + governance columns to `documents`:

| Column | Type | Purpose |
|--------|------|---------|
| `source_url_normalized` | text | Primary identity key |
| `source_filename` | text | Fallback identity key |
| `url_changed_flag` | boolean default false | Human-review flag |
| `last_pulled_at` | timestamptz | Audit of last pull |

Indexes:

- `idx_documents_source_url_norm` on `(source_url_normalized)`
- `idx_documents_fallback` on `(municipality, doc_type, source_filename)`

Backfill: populate `source_url_normalized` + `source_filename` from
existing `source_url` / `local_path` using the shared normalizer
(one-off in the migration or a `scripts/` backfill).

Do not modify any deployed migration. This is additive only.

## Backend

### New crawler — `ingestion/page_crawler.py`

- `discover_asset_links(page_url) -> list[AssetLink]`
  - fetch page HTML via `harvester.fetch_document`
  - parse with BeautifulSoup (already a dep)
  - select `a[href]` ending in supported extensions
  - resolve + normalize each URL
  - de-dupe by normalized URL
- Import boundary: `ingestion/ → db/, stdlib` only. Keep HTTP in harvester helpers.

### New route — `api/routes/pull.py` (prefix `/admin/documents`)

- `POST /pull-page` → returns `{ job_id, status: "processing" }`
- `GET /pull-jobs/{job_id}` → progress + per-file results
- Auth: reuse the **stricter** `_require_admin_auth` (token + role)
  from `admin.py`, not upload's JWT-any-user.
- Body:

```json
{
  "url": "https://city.gov/building/forms",
  "municipality": "dallas",
  "authority_level": "municipal",
  "doc_type": "permit_checklist",
  "subject_tags": ["permits"]
}
```

- Background task per discovered file:
  1. `fetch_document(file_url)` → bytes + content-type
  2. `sha256_bytes(content)`
  3. resolve identity (normalized URL → fallback → new)
  4. `check_document_changed`-style compare on checksum
  5. skip / insert-new / new-version
  6. save raw → chunk → verify → embed (upload's proven order)
  7. on success only: supersede prior version
- Job state: in-memory dict for MVP; note DB-backed table as a later upgrade.

### Ingest flow reuse

Model the per-file worker on `upload._process_upload`
(`api/routes/upload.py` 104–165): `insert_document(draft)` →
`chunk_document(doc_id)` → `delete_chunks_for_document` →
`insert_chunks` → `embed_document(force=True)` →
`update_document_admin_fields(status="active")`.

## Prerequisite fixes (do first)

These are broken today and block a clean pull flow:

1. **`governance._rechunk_and_embed`** (governance.py 184–207) calls
   `chunk_document(raw_path)` (API expects `doc_id`, returns a dict) and
   `embed_and_store` (does not exist). Rewrite to the upload pattern:
   `chunk_document(doc_id)["chunks"]` → `insert_chunks` → `embed_document`.
2. **`upload.py` 238** uses `db_client.get_project` without importing
   `db_client`. Import it or call the already-imported symbol.
3. **Enum drift** — reconcile `upload.VALID_DOC_TYPES` /
   `VALID_AUTHORITY_LEVELS` with `db/schema.sql` enums
   (`permit_guide` vs `permit_checklist`, `regional` not in schema).
   Pull route must validate against the real Postgres enums.

## Format support

| Format | Extract today? | Action |
|--------|----------------|--------|
| PDF | yes | reuse |
| HTML/HTM | yes | reuse |
| DOCX | yes (chunker) | add to allowlist |
| TXT/MD | yes | add to allowlist |
| PPTX | no | add `python-pptx` extractor in chunker |
| legacy `.doc` / `.ppt` | no | out of scope (needs conversion) |

## Security (SSRF + abuse guards)

- HTTPS only
- Block localhost, private/reserved CIDRs, and `169.254.169.254`
- Re-validate host after each redirect
- Per-file size cap + max links per page
- Verify real MIME/type, not just extension
- Request timeouts on every fetch
- Admin-only auth

## Frontend

Add a **Pull from URL** section/tab on `UploadPage.jsx` (`/upload`) —
reuses the existing admin-token field and `status`/`result` UI
(loading → success → error).

| File | Change |
|------|--------|
| `frontend/src/UploadPage.jsx` | URL input + Pull button + per-file result list |
| `frontend/src/api.js` | `pullPage(url, meta)` + `getPullJob(jobId)` helpers |
| `frontend/src/documentAdminUtils.js` | reuse admin headers + session token |

Result UI shows a table: filename, verdict (new / updated / skipped /
flagged / failed), doc_id, and any `url_changed` review flag.

## Governance rules (AGENTS.md)

- Never hard-delete — supersede/repeal only.
- Never ingest without full metadata (municipality, effective_date,
  authority_level, doc_type, review_due, checksum).
- Source URL change → flag for human review, never silent auto-swap.
- A link disappearing from the page → warn, never auto-supersede.
- `registry.json` modified only via governance, never by hand.
- Superseded docs must never be the sole source of an answer.

## Verification checklist

- [ ] `py -m pytest tests/test_url_normalize.py -v`
- [ ] `py -m pytest tests/test_page_crawler.py -v`
- [ ] Migration 022 applies clean on a scratch DB; backfill populates both keys
- [ ] Pull a page with 1 new PDF → ingested, `status=active`, chunks + embeddings present
- [ ] Re-pull same page unchanged → all files skipped
- [ ] Swap a PDF at same URL → new version active, old `superseded`, weight lowered
- [ ] Move a PDF to new URL (same content) → flagged for review, not auto-superseded
- [ ] Extraction failure → new version not activated, old stays active
- [ ] Non-admin token → 401/403
- [ ] SSRF: `http://localhost`, private IP, metadata IP all rejected
- [ ] `cd frontend && npm run test`

## Out of scope (MVP)

- Scheduled/automatic re-pull (watching)
- Recursive multi-page crawl (single page only)
- Legacy `.doc` / `.ppt` conversion
- DB-backed job queue (in-memory for MVP)

## Build order

1. Prerequisite fixes (governance rechunk, upload import, enum drift)
2. `ingestion/url_normalize.py` + tests
3. Migration 022 + backfill
4. `ingestion/page_crawler.py` + tests
5. `api/routes/pull.py` (background worker reusing upload flow)
6. Frontend Pull section on `/upload`
7. End-to-end verification checklist
