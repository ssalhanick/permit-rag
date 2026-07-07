# Sprint 12 P0 — Web Prod Checklist (Separate from Mobile Phase 0)

Track independently from mobile gates in `docs/mobile_phase0_gates.md`.

## Deploy

1. `terraform apply` (CloudFront `/api*` → ALB)
2. Deploy backend + frontend (`npm run deploy` or workflow dispatch)
3. CloudFront invalidation

## Verification (prod)

| P0 | Check | Command / action |
|----|-------|------------------|
| P0-1 | Email+password signup works | Manual: register new user on prod |
| P0-2 | Query returns cited answer | `POST https://permits.scottsalhanick.com/api/query/answer` |
| P0-2 | `GET /api/documents` ≠ `[]` | `$env:ENVIRONMENT="production"; py -m evaluation.prod_preflight` |
| P0-2 | API errors return JSON not HTML | Probe bad path under `/api/*` |
| P0-3 | Mapbox on kickoff wizard | Manual: `/kickoff` autocomplete |
| P0-4 | Hard refresh `/projects` loads SPA | Browser hard refresh, not JSON blob |

## Local preflight (before deploy)

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py tests/test_sprint9.py tests/test_api_main.py tests/test_documents_routes.py tests/test_query_answer_route.py tests/test_purge_project_uploads_script.py -v
cd frontend; npm run test
py -m evaluation.eval_guard
```

## Automated prod smoke script

```powershell
.\scripts\sprint12_p0_smoke.ps1
```
