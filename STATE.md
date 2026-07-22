# permit_rag — State

_Updated: 2026-07-22 (Cognito groups RBAC plan)_

## Phase

**Auth / permissions planning** — Cognito-groups RBAC plan written. URL pull is deployed-ish; next product work can be Phase 0 Cognito groups + Phase 1 sync.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip

## Deliverables checklist

### Cognito Groups RBAC (planned)

- [ ] Plan: [docs/cognito_groups_rbac.md](docs/cognito_groups_rbac.md) + README Planned link
- [ ] Phase 0: create Cognito groups `admin` / `superadmin`; add self; verify `cognito:groups` on access token
- [ ] Phase 1: migration 023 + JWT group → `users.role` sync + staff project read bypass
- [ ] Phase 2: dual-auth corpus routes (Cognito staff or `X-Admin-Token`)
- [ ] Verification checklist in plan doc

### On-demand URL pull (code done prior session)

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip

## Deliverables checklist

### On-demand URL pull (code done this session)

- [x] Prereq fix: `governance._rechunk_and_embed` rewritten to upload pattern (chunk → delete → insert → embed)
- [x] Prereq fix: `upload.py` `db_client.get_project` NameError (now imports `get_project`)
- [x] Prereq fix: enum drift — `upload.py` + `UploadPage.jsx` lists now match `db/schema.sql` (`county` in, `regional` out; real doc_type list)
- [x] `ingestion/url_normalize.py` + `tests/test_url_normalize.py`
- [x] Migration `db/migrations/022_source_identity.sql` (4 columns + 2 indexes) + `scripts/backfill_source_identity.py`
- [x] `ingestion/page_crawler.py` (discover links, SSRF guard, redirect-safe `fetch_asset`) + `tests/test_page_crawler.py`
- [x] Chunker: PPTX extractor (`python-pptx` added to pyproject)
- [x] `db/client.py`: identity lookups + `set_document_source_identity`
- [x] `api/routes/pull.py` — `POST /admin/documents/pull-page` + `GET /pull-jobs/{id}`, strict admin auth, supersede-only-after-embed
- [x] Frontend: Pull-from-URL tab on `/upload`, `pullPage`/`getPullJob` in `api.js`, results table

### Verification (NOT run yet — do first next session)

- [ ] `pip install -e ".[dev]"` (picks up python-pptx)
- [ ] `py -m pytest tests/test_url_normalize.py tests/test_page_crawler.py -v`
- [ ] `py -m pytest tests/test_governance.py tests/test_upload_route.py -v` (prereq regressions)
- [ ] Apply migration 022 local: `py scripts/apply_migration.py db/migrations/022_source_identity.sql`
- [ ] Backfill local: `py scripts/backfill_source_identity.py`
- [ ] Full checklist in [docs/on_demand_url_pull.md](docs/on_demand_url_pull.md) (pull/re-pull/swap/move/SSRF/auth cases)
- [ ] `cd frontend && npm run test`
- [ ] Prod: migration 022 + backfill against RDS, then deploy

## Verification commands

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
py -m pytest tests/test_url_normalize.py tests/test_page_crawler.py tests/test_governance.py tests/test_upload_route.py -v
py scripts/apply_migration.py db/migrations/022_source_identity.sql
py scripts/backfill_source_identity.py
cd frontend; npm run test
```

## Next tasks

1. Run verification checklist above (tests + migration + backfill)
2. Manual pull smoke on a real municipal page via `/upload` Pull tab
3. Prod rollout: migration 022 on RDS + backfill + deploy backend/frontend
4. Optional: iPhone smoke of Sprint 17 flow (deferred)

## Module status

| Module | Current state |
|--------|---------------|
| prod RDS | 19 docs / 17,159 embedded chunks (no migration 022 yet) |
| ingestion | url_normalize + page_crawler new; chunker supports PPTX; governance rechunk fixed |
| api | pull router registered under `/api/admin/documents`; upload enums schema-true |
| db | migration 022 written (not applied); identity helpers in client.py |
| frontend | UploadPage has Upload file / Pull from URL tabs |
| terraform | RDS SG allows campus + home IPs |

## Decisions log

| Decision | Choice |
|----------|--------|
| Doc identity for pull | Normalized source URL first; fallback `municipality + doc_type + filename` with `url_changed` flag |
| Version on content change | New version + supersede old **only after** chunk+embed success |
| Moved URL, same bytes | Flag for review (`url_changed_flag`), never auto-supersede |
| Pull UX | Admin URL + Pull on `/upload`; on-demand only (no watcher) |
| Pull job state | In-memory dict for MVP; DB-backed table later |
| Redirect SSRF | `fetch_asset` disables auto-redirects, re-validates every hop |
| Enum source of truth | `db/schema.sql` enums; upload/pull/frontend lists copied from it |
| Global staff roles | Cognito groups `admin` / `superadmin` → mirror `users.role`; project RBAC stays in RDS; ops token kept as break-glass ([docs/cognito_groups_rbac.md](docs/cognito_groups_rbac.md)) |
| Gen image provider | Leonardo.ai when keyed; OpenAI fallback; mock PNG fallback otherwise |
| Kickoff flow | Deterministic checkbox selections for spaces, work types, and materials |

## Canonical validation

```powershell
py -m pytest tests/test_url_normalize.py tests/test_page_crawler.py -v
# Prod corpus smoke: GET https://permits.scottsalhanick.com/api/documents  (not [])
```
