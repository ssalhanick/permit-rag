# permit_rag — State

_Updated: 2026-07-06 (Sprint 12 closed — deploy + prod verify next)_

## Phase

Sprint 12 closed. Google SSO live on `permits.scottsalhanick.com`. Production UX audit completed 2026-07-03 (`docs/ux_audit_260703.md`). **All P0 fixes coded.** Sprint 12 kickoff wizard + project detail display complete. **Launch blocked on deploy + prod smoke tests only.**

## Blocked on

1. **Deploy stack** — push backend + frontend, `terraform apply` (CloudFront `/api*` behavior), invalidate CDN
2. **Verify P0-1–4 on prod** — registration, query answers, Mapbox autocomplete, `/projects` hard refresh, API errors return JSON not HTML

## Next tasks (priority order)

1. **Deploy stack**: `terraform apply` → `npm run deploy` (or backend + frontend separately) → CloudFront invalidation
2. **Verify on prod**: email+password signup, query answer end-to-end, Mapbox on kickoff wizard, hard refresh `/projects` loads SPA (not JSON), `GET /api/documents` ≠ `[]`
3. **P1 UX fixes**: collaborator dedupe, invite-by-email, jargon copy pass (see audit doc §P1)
4. **Audit cleanup**: delete Cognito user `uxaudit_user1`; delete test project `22cd04d1-a1b8-4b8f-b44a-5287ed09c0bc`
5. **Update Documents**: Add ability/routes to update existing documents
6. **PostGIS**: Add remaining 8 DFW city boundary layers (see `docs/backlog.md`)
7. **Permit determination upgrade**: Swap rule-based `projectPermitRules.js` → RAG query against corpus

## P0 remediation status (2026-07-06)

| P0 | Item | Code | Prod verified |
|----|------|------|---------------|
| P0-1 | Registration username generation | ✅ `authUsername.js`, `AuthContext.jsx`, tests | ⬜ |
| P0-2 | Prod corpus ingest | ✅ `scripts/ingest_prod_corpus.py` | ✅ |
| P0-2 | CloudFront API error scoping | ✅ SPA rewrite on S3 default only; `/api*` → ALB | ⬜ |
| P0-2 | Frontend response-shape guard | ✅ `api.js` rejects HTML-as-JSON | ⬜ |
| P0-3 | Mapbox token in prod build | ✅ `deploy.yml` → `secrets.VITE_MAPBOX_TOKEN` | ⬜ |
| P0-3 | User-neutral fallback copy | ✅ `AddressAutocomplete.jsx` | ⬜ |
| P0-4 | `/projects` route collision | ✅ API namespaced under `/api/*` | ⬜ |

## UX audit deliverables (2026-07-03) — DONE ✅

- [x] Playwright walkthrough of all major paths on prod
- [x] Report: `docs/ux_audit_260703.md`
- [x] Verification: each P0 confirmed via direct API probes
- Audit artifacts: `C:\Users\ssalh\permit_rag_ux_audit\` (outside repo)
- Cleanup pending: Cognito test user `uxaudit_user1`; test project `22cd04d1-a1b8-4b8f-b44a-5287ed09c0bc`

## Sprint 12 deliverables — CLOSED ✅

- [x] `db/migrations/014_project_fields.sql` — adds `address`, `spaces`, `work_types`, `recommended_permits` to projects
- [x] `db/client.py` `create_project()` — accepts 4 new optional fields
- [x] `api/schemas.py` — `CreateProjectRequest` + `ProjectResponse` extended
- [x] `api/routes/projects.py` — passes new fields through
- [x] `frontend/src/projectPermitRules.js` — rule-based permit recommendations
- [x] `frontend/src/ProjectKickoffPage.jsx` — 5-step kickoff wizard
- [x] Auth redirects → `/kickoff` for fresh logins
- [x] Kickoff wizard styles in `styles.css`
- [x] Migration 014 applied (local + RDS)
- [x] Wizard fields visible on project detail (P1-5) — `ProjectKickoffSummary.jsx`, sidebar address hint

**Verification:** `cd frontend; npm run test` (27 pass). Manual: wizard create → `/projects` → confirm address/spaces/work types/permit tags visible.

## Deployment checklist (Sprint 11) — CLOSED ✅

- [x] Local smoke test: Google SSO end-to-end
- [x] Cognito vars in Dockerfile + `deploy.yml`
- [x] RDS migration 013 applied
- [x] Production callback URLs registered (Cognito + Google)
- [x] Google SSO verified on `permits.scottsalhanick.com`

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend ✅ graph ✅

| Module | Current state |
|--------|---------------|
| db | pgvector + PostGIS live; migrations 001–014 applied (local + RDS) |
| rag | Hybrid retrieval (default off); faithfulness gate 0.85 PASS |
| api | All routes under `/api/*`; root `/health` kept for ALB probes |
| graph | Neo4j sync; citation signals via BackgroundTask |
| eval | avg faithfulness **0.910** ✅ |
| frontend | Kickoff wizard + project detail summary; `/api` prefix in `api.js` |

## Current operational snapshot

- **Local corpus:** 13 active docs · 7,170 chunks + embeddings
- **Prod corpus:** ingested (2026-07-06) — verify via `GET /api/documents` or `py -m evaluation.prod_preflight`
- **Vector DB:** Postgres + pgvector on Docker (local) / RDS (prod)
- **Neo4j:** 23 Document nodes, 17,242 Chunk nodes (local sync baseline)
- **Auth:** Cognito RS256; Google SSO + TOTP MFA optional
- **Site:** `https://permits.scottsalhanick.com`

## Quality gates

- Latest eval: `evaluation/results/ragas_20260616_143411.json`
  - avg faithfulness **0.910** ✅ (gate: >= 0.85)
- Eval guard: **PASS** — `py -m evaluation.eval_guard`
- Hybrid retrieval: **OFF** (`RETRIEVAL_HYBRID_ENABLED=false`) — faithfulness 0.810 when on

## Canonical validation commands

```powershell
# Activate venv first
.\.venv\Scripts\Activate.ps1

# 1. Full test suite
py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py tests/test_sprint9.py tests/test_api_main.py tests/test_documents_routes.py tests/test_query_answer_route.py tests/test_purge_project_uploads_script.py -v

# 2. Frontend unit tests
cd frontend; npm run test

# 3. Prod corpus preflight
$env:ENVIRONMENT="production"; py -m evaluation.prod_preflight

# 4. Health check (ALB probe path — unchanged)
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get

# 5. Eval guard
py -m evaluation.eval_guard
```
