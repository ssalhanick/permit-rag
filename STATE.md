# permit_rag — State

_Updated: 2026-06-30 (Sprint 11 — Cognito smoke-tested locally, deploying to production)_

## Phase

Sprint 11 complete + locally validated. **93 tests passing.** Google SSO end-to-end confirmed locally. Deploying to production.

## Blocked on

*None*

## Next tasks

1. **RDS migration pending**: `$env:ENVIRONMENT="production"; py scripts\run_migration.py db\migrations\013_cognito_auth.sql` (needs RDS SG open to local IP)
2. **Register production callback URL**: Add `https://permits.scottsalhanick.com/auth/callback` to Cognito App Client + Google Cloud Console authorized redirect URIs
3. **Update Documents**: Add ability/routes to update existing documents
4. **PostGIS**: Add remaining 8 DFW city boundary layers (see `docs/backlog.md`)

## Deployment checklist (Sprint 11)

- [x] Local smoke test: Google SSO end-to-end confirmed
- [x] `Dockerfile` — baked in `COGNITO_USER_POOL_ID` + `COGNITO_REGION`
- [x] `deploy.yml` — Cognito vars injected into frontend Vite build
- [x] `frontend/.env.production` — created (gitignored; vars in workflow instead)
- [ ] RDS migration 013 applied to production
- [ ] Production callback URL registered in Cognito + Google

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend ✅ graph ✅

| Module | Current state |
|--------|---------------|
| db | pgvector + PostGIS live; `corpus_writer`/`app_reader` roles; migrations 001–010 applied; `db/graph_client.py` singleton Bolt driver |
| rag | Hybrid retrieval; provenance reranker; multi-permit classifier; jurisdiction resolver; conflict detector (lightweight + graph-backed) |
| api | `/query`, `/query/answer`, `/health` (+ `graph_health`), `/documents/*`, `/admin/*`, `/upload`, `/auth/me`; LangSmith tracing; BackgroundTask graph citation signals; Cognito RS256 JWT verification |
| graph | Neo4j CE in docker-compose; constraints + indexes applied; Postgres→Graph sync via `scripts/sync_graph.py`; cross-authority Cypher traversal; citation signal enrichment (`record_cited_chunks`) |
| eval | RAGAs eval + guard live; baseline `ragas_20260531_122639.json`; faithfulness gate `>= 0.85` |
| frontend | Vite+React; chat/citation viewer; document browser; upload UX; address autocomplete; conflict warnings panel; Cognito auth (email+password, Google SSO, TOTP 2FA) |

## Current operational snapshot

- Vector DB: Postgres + pgvector (`chunks.embedding vector(768)`) + PostGIS (durable Docker image)
- DB roles: `corpus_writer` (ingestion), `app_reader` (API reads + query_log)
- Neo4j: `bolt://localhost:7687`, 23 Document nodes, 17,242 Chunk nodes, 7 Municipality nodes, 3 AuthorityLevel nodes
- Graph sync: `py -m scripts.sync_graph` (supports `--dry-run`, `--municipality`, `--doc-id`)
- Docs corpus: 13 active · 0 superseded · 10 ingested · 7,170 chunks + embeddings

## Quality gates

- Latest eval: `evaluation/results/ragas_20260616_143411.json` _(Sprint 6/7 checkpoint)_
  - avg faithfulness `0.910` ✅ (gate: `>= 0.85`)
  - avg relevancy `0.689` ✅ | avg context precision `0.654`
  - q1 faithfulness `0.875` (baseline `0.600`) ✅
- Eval guard: **PASS** — `py -m evaluation.eval_guard`
- Cache policy: `RAGAS_ANSWER_CACHE_ENABLED=false` for all eval runs

## Sprint 11 deliverables (closed)

- [x] DB migration `013_cognito_auth.sql` — TRUNCATE users, drop `password_hash`/`refresh_token_hash`/`token_family`, add `cognito_sub TEXT UNIQUE NOT NULL`
- [x] `api/auth.py` — full rewrite: `verify_cognito_token()` with cached JWKS, `get_current_user` lazy-provisions RDS row via `get_or_create_cognito_user()`
- [x] `api/routes/auth.py` — stripped to `GET /auth/me` only
- [x] `db/client.py` — replaced 5 password-based helpers with `get_or_create_cognito_user()` (email fallback for account linking)
- [x] `pyproject.toml` — swapped `argon2-cffi` + `PyJWT` + `phonenumbers` → `python-jose[cryptography]`
- [x] `frontend/src/context/AuthContext.jsx` — Cognito SDK: email+password, Google SSO redirect, TOTP MFA challenge + enrollment, auto-refresh via `getSession()`
- [x] `frontend/src/AuthPage.jsx` — 5-screen state machine: login, register, email confirm, MFA challenge, MFA setup QR
- [x] `frontend/src/AuthCallback.jsx` — new file: handles `/auth/callback` OAuth2 code exchange
- [x] `frontend/src/main.jsx` — added `/auth/callback` route
- [x] `frontend/src/api.js` — `registerTokenRefresher` callback, removed custom `/auth/refresh` logic
- [x] `scripts/run_migration.py` — utility for applying SQL migration files
- [x] `tests/test_sprint9.py` — replaced Argon2id/JWT unit tests with `TestCognitoVerification`; updated `auth_headers` fixture

## Active decisions

- **Governance**: documents never deleted — `active/superseded/repealed/needs_ocr/draft` lifecycle only.
- **Retrieval**: hybrid dense+BM25 enabled by default; env toggle for rollback.
- **Auth**: Cognito RS256 JWKS verification (`python-jose`). JWKS cached 1 hour, re-fetched on unknown `kid`. `get_current_user` lazy-provisions RDS row on first login. Google SSO via Authorization code grant + Cognito hosted UI. TOTP MFA optional (user self-enrolls).
- **Security**: admin routes require token + role allowlist (`API_ADMIN_AUTH_REQUIRED=true`). Rotate `API_ADMIN_TOKEN` every 30 days.
- **Purge tiers**: `source_tier=3` purge = normal admin; lower tiers need `API_PURGE_ANY_TIER_ROLES`.
- **CORS**: env-driven allowlist (`API_CORS_ALLOW_ORIGINS`); wildcard only via `API_CORS_ALLOW_ALL=true`.
- **DB roles**: rotate passwords before any shared deployment; prod → Supabase service_role/anon RLS.
- **Graph health**: `graph_health` in `/health` is additive — Neo4j down does not flip `status` to `unhealthy`.
- **Graph citation signals**: `record_cited_chunks()` fires as `BackgroundTask` after `/query/answer` — zero latency impact; non-raising.
- **Hybrid retrieval**: `RETRIEVAL_HYBRID_ENABLED=false` default retained — BM25 A/B eval showed hybrid faithfulness `0.810` < gate `0.850` (dense-only `0.910`). Relevancy improved +0.127 but faithfulness gap is disqualifying. Future path: tune `RETRIEVAL_RRF_BM25_WEIGHT < 1.0`.
- **Eval baseline**: do not change baseline file without a deliberate sprint gate review.

## Sprint 8 deliverables (closed)

- [x] Task 16F: `record_cited_chunks()` in `db/graph_client.py` — `(:Query)-[:CITED]->(:Chunk)` edges; stamps `last_cited_at`, `last_cited_query`, `citation_count` on cited Chunk nodes
- [x] Task 16F: wired via `BackgroundTasks` in `api/routes/query.py` — fires after HTTP response, zero latency impact
- [x] `tests/test_sprint8.py` — 12 tests → **72 total** ✅
- [x] Live validation: `GET /health` → `graph_health=True` ✅ | eval guard PASS ✅
- [x] BM25 A/B eval: hybrid faithfulness `0.810` < gate `0.850` — dense-only `RETRIEVAL_HYBRID_ENABLED=false` retained
## Sprint 10 deliverables (closed)

- [x] Responsive layout styling for mobile, tablet, and desktop viewports using industry-standard rem breakpoints.
- [x] Collapsible responsive navigation bar (`Nav.jsx` with burger toggle state and header wrapper).
- [x] Table horizontal scroll wrapper (`doc-table-wrap`) applied across all data tables (Document Browser and Projects panels).
- [x] Touch target size optimizations to meet WCAG AAA accessibility conformance (minimum 44px height for all buttons, inputs, links, list elements, and autocomplete options).
- [x] Mapbox Search Box API integration: implemented required session_token UUID generation and rotation logic to support address geocoding suggestions and retrievals.

## Sprint 9 deliverables (closed)

- [x] JWT Auth & Verification primitives (`api/auth.py`) — Argon2id password hashing, E.164 phone formatting, strict visual-safety username validation rules.
- [x] Session & JWT Tokens — access and refresh tokens, refresh token hashing in DB, token family rotation (reuse prevention), logout-all-sessions.
- [x] Project CRUD & Lifecycle — Projects table, project members table with roles (owner, editor, viewer), ownership transfer, cascading deletion.
- [x] Document Sharing & Binding — Project documents join table, RBAC checks on sharing, binding on upload (via optional project_id form field).
- [x] Query History & Deletion — Private, user-scoped query history logging and single-query deletion controls.
- [x] React Frontend Integration — Wired JWT login/register, token auto-refresh interceptor, project workspace manager, collaborator role controls, query histories, and document management.
- [x] `tests/test_sprint9.py` — 21 tests → **93 total** ✅

## Sprint 7 deliverables (closed)

- [x] Task 16D: `graph_health: bool` in `GET /health` — non-blocking `ping()`, additive only
- [x] Task 16E: `find_cross_authority_conflicts()` Cypher traversal in `db/graph_client.py`
- [x] Task 16E: `detect_conflicts_with_graph()` in `rag/conflict_detector.py` — graph Tier B path with lightweight fallback
- [x] `tests/test_sprint7.py` — 20 tests → **60 total** ✅

_For full per-task history see journals/session_260616a.md (Sprint 6), journals/session_260616b.md (Sprint 7), journals/session_260616c.md (Sprint 8 Task 16F)._

## Canonical validation commands

```powershell
# 1. Full test suite
py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py tests/test_sprint8.py tests/test_sprint9.py -v

# 2. Health check (API must be running)
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get

# 3. Eval guard (no regression)
py -m evaluation.eval_guard

# 4. Full RAGAs eval export
$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export

# 5. Graph sync dry-run
py -m scripts.sync_graph --dry-run

# 6. BM25 A/B eval (Sprint 8)
$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export

# 7. Frontend tests
cd frontend; npm run test
```

