# permit_rag — State

_Updated: 2026-06-16b (Sprint 7 close)_

## Phase

Sprint 7 closed. **60 tests passing.** All graph layer tasks (16A–16E) live.

## Blocked on

- **Mapbox token**: `VITE_MAPBOX_TOKEN` not set in `frontend/.env` — autocomplete degrades to plain text. See `frontend/.env.example`.

## Next tasks

1. Sprint 8 — Task 16F (optional): tag cited chunks as graph nodes after each `/query/answer` call
2. Sprint 8 — BM25 A/B eval: measure hybrid vs dense-only retrieval quality delta
3. Sprint 8 — Add remaining 8 DFW city boundary layers to PostGIS (see `docs/backlog.md`)

## Module status

ingestion ✅ db ✅ rag ✅ api ✅ eval ✅ frontend ✅ graph ✅

| Module | Current state |
|--------|---------------|
| db | pgvector + PostGIS live; `corpus_writer`/`app_reader` roles; migrations 001–010 applied; `db/graph_client.py` singleton Bolt driver |
| rag | Hybrid retrieval; provenance reranker; multi-permit classifier; jurisdiction resolver; conflict detector (lightweight + graph-backed) |
| api | `/query`, `/query/answer`, `/health` (+ `graph_health`), `/documents/*`, `/admin/*`, `/upload`; LangSmith tracing |
| graph | Neo4j CE in docker-compose; constraints + indexes applied; Postgres→Graph sync via `scripts/sync_graph.py`; cross-authority Cypher traversal |
| eval | RAGAs eval + guard live; baseline `ragas_20260531_122639.json`; faithfulness gate `>= 0.85` |
| frontend | Vite+React; chat/citation viewer; document browser; upload UX; address autocomplete; conflict warnings panel |

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

## Active decisions

- **Governance**: documents never deleted — `active/superseded/repealed/needs_ocr/draft` lifecycle only.
- **Retrieval**: hybrid dense+BM25 enabled by default; env toggle for rollback.
- **Security**: admin routes require token + role allowlist (`API_ADMIN_AUTH_REQUIRED=true`). Rotate `API_ADMIN_TOKEN` every 30 days.
- **Purge tiers**: `source_tier=3` purge = normal admin; lower tiers need `API_PURGE_ANY_TIER_ROLES`.
- **CORS**: env-driven allowlist (`API_CORS_ALLOW_ORIGINS`); wildcard only via `API_CORS_ALLOW_ALL=true`.
- **DB roles**: rotate passwords before any shared deployment; prod → Supabase service_role/anon RLS.
- **Graph health**: `graph_health` in `/health` is additive — Neo4j down does not flip `status` to `unhealthy`.
- **Eval baseline**: do not change baseline file without a deliberate sprint gate review.

## Sprint 7 deliverables (current sprint)

- [x] Task 16D: `graph_health: bool` in `GET /health` — non-blocking `ping()`, additive only
- [x] Task 16E: `find_cross_authority_conflicts()` Cypher traversal in `db/graph_client.py`
- [x] Task 16E: `detect_conflicts_with_graph()` in `rag/conflict_detector.py` — graph Tier B path with lightweight fallback
- [x] `tests/test_sprint7.py` — 20 tests → **60 total** ✅
- [x] Live validation: `GET /health` → `graph_health=True` ✅ | eval guard PASS ✅

_For full per-task history see `journals/session_260616a.md` (Sprint 6) and `journals/session_260616b.md` (Sprint 7)._

## Canonical validation commands

```powershell
# 1. Full test suite
py -m pytest tests/test_sprint5.py tests/test_sprint6.py tests/test_sprint7.py -v

# 2. Health check (API must be running)
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get

# 3. Eval guard (no regression)
py -m evaluation.eval_guard

# 4. Full RAGAs eval export
$env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export

# 5. Graph sync dry-run
py -m scripts.sync_graph --dry-run

# 6. Frontend tests
cd frontend; npm run test
```
