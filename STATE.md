# permit_rag — State

_Updated: 2026-07-21 (Prod corpus ingest + URL pull plan)_

## Phase

**Sprint 17 wrap + ingestion tooling** — Prod RDS corpus seeded. Next: on-demand URL pull feature.

## Blocked on

1. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip

## Deliverables checklist

### Prod corpus (done this session)

- [x] RDS security group: home IP `68.20.22.215/32` + campus IP in terraform
- [x] `terraform apply` for SG ingress (no DB recreate)
- [x] Prod harvest → ingest → embed via `scripts/ingest_prod_corpus.py`
- [x] Fix `_verify_counts` KeyError (`dict_row` → alias `AS n`)
- [x] Verify RDS: **19 active docs, 17,159 chunks, 17,159 embedded**
- [x] Plan doc: [docs/on_demand_url_pull.md](docs/on_demand_url_pull.md) + README Planned link

### On-demand URL pull (next)

- [ ] Prerequisite fixes: governance rechunk helper, upload `db_client` import, enum drift
- [ ] `ingestion/url_normalize.py` + tests
- [ ] Migration `022_source_identity.sql` + backfill
- [ ] `ingestion/page_crawler.py` + tests
- [ ] `POST /admin/documents/pull-page` + job poll
- [ ] UploadPage Pull-from-URL UI
- [ ] Verification checklist in plan doc

## Verification

**Prod corpus:**
```powershell
$env:ENVIRONMENT="production"; & .\.venv\Scripts\python.exe scripts\ingest_prod_corpus.py
# Expected log: RDS corpus: 19 active docs, 17159 chunks (17159 embedded)
# Smoke: https://permits.scottsalhanick.com/api/documents  (not [])
```

**URL pull (after implementation):** see checklist in `docs/on_demand_url_pull.md`

## Next tasks

1. Start URL pull build order from plan (prereq fixes first)
2. Optional: iPhone smoke of Sprint 17 flow (deferred)

## Module status

| Module | Current state |
|--------|---------------|
| prod RDS | 19 docs / 17,159 embedded chunks |
| terraform | RDS SG allows campus + home IPs |
| ingest scripts | `_verify_counts` dict_row-safe |
| docs | `on_demand_url_pull.md` planned |

## Decisions log

| Decision | Choice |
|----------|--------|
| Doc identity for pull | Normalized source URL first; fallback `municipality + doc_type + filename` with `url_changed` flag |
| Version on content change | New version + supersede old **only after** chunk+embed success |
| Pull UX | Admin URL + Pull on `/upload`; on-demand only (no watcher) |
| Gen image provider | Leonardo.ai when keyed; OpenAI fallback; mock PNG fallback otherwise |
| Kickoff flow | Deterministic checkbox selections for spaces, work types, and materials |

## Canonical validation

```bash
$env:ENVIRONMENT="production"; & .\.venv\Scripts\python.exe scripts\ingest_prod_corpus.py
# API smoke: GET https://permits.scottsalhanick.com/api/documents
```
