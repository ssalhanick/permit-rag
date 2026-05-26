# Session: 2026-05-26 (b)

## Type

Build — rag/pipeline.py dense retrieval + manual eval.

## Goal

Build retrieval pipeline, test with sample queries, evaluate quality before wiring API layer.

---

## Completed

### Built rag/retriever.py

- `RetrievalResult` dataclass with diagnostics (top_sim, mean_sim, unique_docs, latency)
- `retrieve()` function: embed_query → match_chunks → return ranked chunks
- Respects AGENTS.md import boundaries (rag → db, ingestion.embedder)

### Added match_chunks() to db/client.py

- Python wrapper for the `match_chunks()` SQL function (schema.sql)
- Calls pgvector HNSW cosine search via the SQL function
- Supports municipality filter and client-side min_similarity floor

### Built rag/pipeline.py

- `retrieve_and_display()`: single query with pretty-printed output
- `batch_eval()`: 7 predefined test queries with quality assessment
- Quality heuristics: good/weak/miss verdicts based on similarity thresholds
- CLI: `py -m rag.pipeline "query"` and `py -m rag.pipeline --batch`

### Batch evaluation results (dense-only baseline)

| Query | Verdict | Top Sim | N | Docs | Latency |
|---|---|---|---|---|---|
| Fence setback (Dallas) | ✅ | 0.762 | 10 | 2 | 9603ms* |
| Electrical permit (TX) | ✅ | 0.790 | 10 | 4 | 106ms |
| ADA accessibility | ✅ | 0.814 | 10 | 6 | 112ms |
| Stormwater mgmt | ✅ | 0.796 | 10 | 3 | 94ms |
| Building permits (Plano) | ⚠️ | 0.704 | 1 | 1 | 64ms |
| Fire sprinklers (Dallas) | ✅ | 0.768 | 10 | 3 | 106ms |
| Building height (Dallas) | ✅ | 0.803 | 10 | 1 | 100ms |

*First query includes model loading. Steady-state is 64–112ms.

**Summary:** 6 good, 1 weak, 0 miss. Plano weak is data coverage (1 chunk), not retrieval quality.

### Resolved local Postgres port conflict

- Local Windows Postgres 18 was listening on port 5433, intercepting connections meant for Docker
- Killed the process, disabled both PG 16 and PG 18 Windows services (StartupType → Disabled)
- Set Docker container pg_hba.conf to `trust` for TCP connections (local dev only)

---

## Files changed

- db/client.py (added `match_chunks()` wrapper function)
- rag/retriever.py (built from scratch — RetrievalResult + retrieve())
- rag/pipeline.py (built from scratch — display, quality assessment, CLI, batch eval)
- STATE.md (updated module status, next tasks, retrieval baseline, decisions)
- journals/session_260526b.md (created)

## Files NOT changed

- rag/generator.py, rag/reranker.py, rag/conflict_detector.py (still empty stubs)
- db/schema.sql (no schema changes)
- ingestion/* (no changes)

---

## Decisions made

- Local Windows Postgres services (16+18) disabled — Docker is sole DB for dev
- Dense retrieval quality sufficient for API layer — hybrid search still deferred to Week 4–5
- Retrieval baseline recorded: 6/7 good on 7 test queries with dense-only

---

## Next session should

1. Build api/ — FastAPI endpoints for query and document management
2. Build rag/generator.py — Claude-powered answer generation with citations
3. Begin evaluation/ — RAGAs integration for retrieval quality metrics

## Prompt for next session

Read STATE.md and journals/session_260526b.md. Build api/ with FastAPI:
a POST /query endpoint that calls rag/pipeline.py retrieve() and returns
ranked chunks with metadata. Add a GET /health endpoint. Use Pydantic
models for request/response schemas. Test with curl or the Swagger UI.
If time allows, start rag/generator.py to produce cited answers via Claude.

## Git commit message

feat(rag): build dense retrieval pipeline with match_chunks, retriever, batch eval CLI — 6/7 good on baseline test queries, resolve local Postgres port conflict with Docker
