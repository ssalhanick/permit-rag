# permit_rag — State

_Updated: 2026-05-26_

## Phase

Week 1 of 9 — Foundation

## Blocked on

Nothing currently

## Next 3 tasks

1. Build api/ — FastAPI endpoints for query and document management
2. Begin evaluation/ — RAGAs integration for retrieval quality metrics
3. Build rag/generator.py — Claude-powered answer generation with citations

## Module status

ingestion ✅ db ✅ rag 🔶 api ⏳ eval ⏳ frontend ⏳

_rag note: retriever + pipeline done (dense-only); generator + reranker + conflict_detector still ⏳_

## Ingestion verification (last run: 2026-05-25)

download ✅ extraction ✅ chunking ✅ embedding ✅

## Retrieval baseline (2026-05-26, dense-only, 7 test queries)

good 6 · weak 1 · miss 0 · avg latency 1455ms (incl. model load)
top_sim range: 0.704–0.814 · mean_sim range: 0.704–0.793
weak = Plano (1 chunk in DB — data coverage, not retrieval quality)

## RAGAs (last run: never)

faithfulness — relevancy — precision — recall —

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
