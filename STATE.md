# permit_rag — State

_Updated: 2026-05-31 (authority guardrails + full-suite recheck)_

## Phase

Week 2 of 9 (calendar) — Evaluation active (Phase 4 deliverables pulled forward)

## Blocked on

Nothing currently

## Next 3 tasks

1. Build `api/routes/documents.py` — document listing/status endpoints + response schemas
2. Add tests for document route filtering (municipality/status/authority/doc_type) and detail responses
3. Add API docs + README endpoint examples for document listing and status inspection

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

## RAGAs (latest: 2026-05-31 hybrid guardrail rerun)

full run summary (2026-05-29, dense-only baseline; `ragas_20260529_222152.json`):
- avg faithfulness 0.855 · avg relevancy 0.401 · avg context precision 0.534
- per-query faithfulness: q0 0.750 · q1 0.864 · q2 0.938 · q3 1.000 · q4 0.895 · q5 0.667 · q6 0.875

hybrid tuning profile A:
- `RETRIEVAL_RRF_DENSE_WEIGHT=1.4`
- `RETRIEVAL_RRF_BM25_WEIGHT=0.6`
- `RETRIEVAL_DENSE_TOP_N=24`
- `RETRIEVAL_BM25_TOP_N=10`
- `RETRIEVAL_PROCEDURAL_PENALTY_ENABLED=true`
- `RETRIEVAL_PROCEDURAL_PENALTY=0.02`
- `RETRIEVAL_PROCEDURAL_MAX_HITS=4`
- plus non-municipality authority guardrails (`RETRIEVAL_AUTHORITY_GUARDRAIL_*`)

hybrid subset rerun (q0,q1,q2,q3,q5; `ragas_20260531_094718.json`):
- avg faithfulness 0.784 (delta vs prior hybrid subset 0.813: -0.029)
- avg relevancy 0.778
- avg context precision 0.663
- q1 faithfulness 0.588 (improved vs prior hybrid subset q1=0.353, but still below baseline)

hybrid full rerun (7-query; `ragas_20260531_102544.json`):
- avg faithfulness 0.852 (PASS vs 0.85 gate; +0.054 vs prior hybrid full 0.798; -0.003 vs dense baseline 0.855)
- avg relevancy 0.832 (+0.008 vs prior hybrid full; +0.431 vs dense baseline)
- avg context precision 0.621 (+0.018 vs prior hybrid full; +0.087 vs dense baseline)
- per-query faithfulness: q0 0.778 · q1 0.438 · q2 0.947 · q3 1.000 · q4 1.000 · q5 1.000 · q6 0.800

key takeaway:
- full-suite faithfulness recovered above gate on the latest run (`0.852`)
- q1 remains the weakest query and still shows cross-jurisdiction contamination risk in retrieval previews
- answer cache remained disabled (`RAGAS_ANSWER_CACHE_ENABLED=false`) during tuning/validation runs

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
- Hybrid search rollout gate: require full-suite avg faithfulness >= 0.85 and no severe single-query grounding collapse before default enablement
- `RETRIEVAL_HYBRID_ENABLED` remains false for now despite latest full run pass (0.852) due to unstable q1 grounding; re-check after API work with one additional confirmatory full run
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
- Retrieval now supports non-municipality authority guardrails (`RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED`) to penalize municipal noise and prefer state/federal scope alignment on statewide/federal queries

## Deliverables checklist

- [x] Investigated q1 faithfulness collapse under hybrid retrieval
- [x] Added retrieval-time authority/source guardrails for non-municipality queries
- [x] Ran `rag.pipeline` previews for q1 and q5 under hybrid mode
- [x] Ran `py -m evaluation.ragas_eval --query 0 1 2 3 5 --export`
- [x] Ran `py -m evaluation.ragas_eval --export` (full 7-query)
- [x] Recorded metric deltas and rollout decision in state
- [x] Added export support for `most_relevant_chunk_id` and `most_relevant_doc_id` in eval output

## Validation / verification steps

1. `py -m pytest tests/test_retriever.py` → pass (`6 passed`)
2. `$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m rag.pipeline --top-k 10 "Do I need a permit for electrical work in Texas?"`
3. `$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m rag.pipeline --municipality dallas --top-k 10 "What are the fire sprinkler requirements for new construction in Dallas?"`
4. `$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --query 0 1 2 3 5 --export` → `evaluation/results/ragas_20260531_094718.json`
5. `$env:RETRIEVAL_HYBRID_ENABLED="true"; $env:RAGAS_ANSWER_CACHE_ENABLED="false"; py -m evaluation.ragas_eval --export` → `evaluation/results/ragas_20260531_102544.json`
