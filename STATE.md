# permit_rag — State

_Updated: 2026-05-31 (hybrid sweep validation + gate decision)_

## Phase

Week 2 of 9 (calendar) — Evaluation active (Phase 4 deliverables pulled forward)

## Blocked on

Nothing currently

## Next 3 tasks

1. Isolate and fix q1 faithfulness regression under hybrid retrieval (statewide electrical permit query)
2. Add retrieval-time source/authority guardrails for non-municipality queries to reduce cross-jurisdiction noise
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

## RAGAs (latest: 2026-05-31 hybrid sweep + full gate check)

full run summary (2026-05-29, dense-only): avg faithfulness 0.855 · avg relevancy 0.401 · avg context precision 0.534
faithfulness gate on dense-only baseline: PASS (0.855 >= 0.85)
per-query faithfulness: q0 0.750 · q1 0.864 · q2 0.938 · q3 1.000 · q4 0.895 · q5 0.667 · q6 0.875
hybrid tuning profile A (2026-05-30):
- RETRIEVAL_RRF_DENSE_WEIGHT=1.4
- RETRIEVAL_RRF_BM25_WEIGHT=0.6
- RETRIEVAL_DENSE_TOP_N=24
- RETRIEVAL_BM25_TOP_N=10
- RETRIEVAL_PROCEDURAL_PENALTY_ENABLED=true
- RETRIEVAL_PROCEDURAL_PENALTY=0.02
- RETRIEVAL_PROCEDURAL_MAX_HITS=4
focused run (q0,q1,q2,q3,q5; `ragas_20260530_232025.json`):
- avg faithfulness 0.813 (vs dense-only subset baseline 0.844, delta -0.031)
- avg relevancy 0.787
- avg context precision 0.690
- per-query faithfulness deltas vs dense-only: q0 -0.036 · q1 -0.511 · q2 +0.062 · q3 +0.000 · q5 +0.333
full gate run (7-query; `ragas_20260531_003019.json`):
- avg faithfulness 0.798 (FAIL vs 0.85 gate; delta vs dense-only -0.057)
- avg relevancy 0.824 (delta +0.423)
- avg context precision 0.603 (delta +0.069)
- per-query faithfulness: q0 0.778 · q1 0.353 · q2 0.867 · q3 0.842 · q4 1.000 · q5 1.000 · q6 0.750
key takeaway: hybrid tuning recovered weak-query targeting on q5 but introduced severe q1 grounding regression that pulls full-suite faithfulness below gate
answer cache: disabled for tuning (`RAGAS_ANSWER_CACHE_ENABLED=false`) during subset/full validation runs
langsmith tracing: eval-local tracing remains enabled for retrieval/generation/scoring inspection

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
- Hybrid search implemented behind `RETRIEVAL_HYBRID_ENABLED` with dense+BM25 RRF fusion and rollback-safe default-off behavior
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
- Hybrid search rollout remains gated: keep disabled by default until hybrid-on faithfulness returns to >= 0.85 on full suite
- `RETRIEVAL_HYBRID_ENABLED` remains false after 2026-05-31 sweep because full hybrid faithfulness is 0.798 (< 0.85 gate)
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
- Ingestion normalization is now env-gated (`CHUNK_NORMALIZATION_ENABLED`) with procedural line stripping + balanced chunk filtering
- Retrieval now supports env-gated procedural downranking (`RETRIEVAL_PROCEDURAL_PENALTY_ENABLED`) to demote boilerplate-heavy chunks
