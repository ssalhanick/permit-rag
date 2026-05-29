# permit_rag — State

_Updated: 2026-05-28 (session, LangSmith eval tracing update)_

## Phase

Week 2 of 9 (calendar) — Evaluation active (Phase 4 deliverables pulled forward)

## Blocked on

Nothing currently

## Next 3 tasks

1. Stabilize RAGAs faithfulness scoring (increase evaluator token budget) and rerun full 7-query suite
2. Add POST /query/answer endpoint wiring generator → API (requires ANTHROPIC_API_KEY in .env)
3. Build api/routes/documents.py — document listing/status endpoints

## Module status

ingestion ✅ db ✅ rag 🔶 api 🔶 eval 🔶 frontend ⏳

_rag note: retriever + pipeline + generator done; reranker + conflict_detector still ⏳_
_api note: POST /query + GET /health live; documents + admin routes still ⏳_

## Ingestion verification (last run: 2026-05-25)

download ✅ extraction ✅ chunking ✅ embedding ✅

## Retrieval baseline (2026-05-26, dense-only, 7 test queries)

good 6 · weak 1 · miss 0 · avg latency 1455ms (incl. model load)
top_sim range: 0.704–0.814 · mean_sim range: 0.704–0.793
weak = Plano (1 chunk in DB — data coverage, not retrieval quality)

## API baseline (2026-05-26, tested via Swagger UI)

GET /health → {"status":"healthy","database":true,"version":"0.1.0"}
POST /query → 200 OK, 5 chunks, top_sim 0.762, 2 unique docs (dallas fence query)
First-request latency ~29s (model load); steady-state 64–112ms
Pydantic schemas: QueryRequest, QueryResponse, ChunkResponse, DiagnosticsResponse, HealthResponse, ErrorResponse
Swagger UI: http://localhost:8000/docs

## RAGAs (last run: 2026-05-27, full + cache validation)

smoke (query 0): faithfulness 0.778 · relevancy 0.000 · context precision 0.200
partial full run: relevancy now computes (observed 0.000 and 0.996 on sampled queries)
known issue: faithfulness intermittently fails with LLMDidNotFinishException (increase evaluator max_tokens)
answer caching: strict-key generation cache enabled for eval reruns
cache validation: query 0 run 1 = miss (0 hit / 1 miss), run 2 = hit (1 hit / 0 miss)
prompt caching rollout: Anthropic explicit-breakpoint path wired for generator + evaluator
prompt caching observation: evaluator usage logs currently show cache create/read=0/0 on sampled calls (instrumented, no cache benefit yet)
langsmith tracing: eval-only instrumentation added in `evaluation/ragas_eval.py` (run + per-query + retrieval/generation/scoring spans)
langsmith validation: traces visible in LangSmith project for smoke eval; tracing remains no-op when env flags/API key are unset

## Docs

13 active · 0 superseded · 0 overdue · last harvest 2026-05-22
10 pass chunking · 3 fail extraction (Municode redirect pages)
10 docs ingested · 7,170 chunks · 7,170 embeddings (100% coverage)

## Decisions

- Local Postgres 18 + pgvector for dev; Supabase or RDS for production deploy
- psycopg3 (direct driver) over Supabase SDK — no vendor lock-in, portable to any Postgres host
- Docker Compose for local Postgres + pgvector (pgvector/pgvector:pg17 image)
- Docker mapped to port 5433 to avoid conflict with local Windows Postgres on 5432
- FastAPI over Flask (async support, auto OpenAPI docs)
- Vite + React over Next.js (simpler for MVP, deploys free on Vercel)
- Claude API for generation; nomic-embed-text-v1.5 for embeddings (local, free)
- nomic-embed-text-v1.5 over Voyage-3: no API key, no cost, 768-dim, local inference
- Hybrid search planned: dense (nomic) + BM25 for future retrieval quality
- Dallas + Fort Worth use amlegal not Municode (codelibrary.amlegal.com)
- Plano, McKinney, Frisco confirmed on Municode
- up.codes added for Fort Worth amendment tracking
- Citations must reference publisher + date, never imply direct city authority
- verification.py runs at every ingestion stage — no silent failures
- Scanned PDFs flagged as needs_ocr, not ingested until OCR run
- Verification results written to registry.json per document
- Dallas amlegal export requires manual PDF download (bot protection)
- Dallas code split into 4 documents: charter + 3 ordinance volumes
- Chunking: 1500 chars / 200 overlap, RecursiveCharacterTextSplitter
- No tokenization/lemmatization — dense embedding models handle semantics internally
- Chunk size to be empirically tuned via RAGAs ablation in Week 4–5
- tsvector GENERATED column + GIN index added to chunks table for future BM25 hybrid search
- Hybrid search (HNSW + BM25 RRF) deferred to Week 4–5 RAGAs ablation — build dense-only first
- Hatchling build with explicit packages list (no single-package layout)
- psycopg-pool is a separate package from psycopg (added to pyproject.toml)
- Schema doc_type enum expanded: added state_statute + federal_regulation
- Schema vector column: 768-dim (nomic) not 1024-dim (voyage)
- Local Windows Postgres 16+18 services disabled — Docker is sole DB for dev
- Dense retrieval quality sufficient for API layer — hybrid search still deferred to Week 4–5
- API CORS set to allow_origins=["*"] for local dev — must tighten for production
- Generator system prompt enforces [doc_id, chunk N] citation format — regex extraction in _extract_citations()
- Lifespan pattern (not @app.on_event) for startup/shutdown — compatible with FastAPI 0.111+
- RAGAs relevancy embedding adapter now uses LangchainEmbeddingsWrapper composition (not subclassing HuggingfaceEmbeddings)
- Preferred eval dependency path is langchain-huggingface with langchain_community fallback import
- Eval answer cache strategy: generation-only cache with strict key (query + retrieval fingerprint + model + prompt version)
- LLM provider capability layer added (`LLM_PROVIDER` + `supports_prompt_caching`) so prompt caching is optional and Anthropic-specific
- Anthropic prompt caching uses explicit system-block breakpoints (`cache_control`) gated by provider capability + env flag
- LangSmith tracing scope is eval-local only (gated by `LANGCHAIN_TRACING_V2` + `LANGSMITH_API_KEY`) with full payload capture for prompt/metric debugging
