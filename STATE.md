# permit_rag — State

_Updated: 2026-05-20_

## Phase

Week 1 of 9 — Foundation

## Blocked on

Nothing currently

## Next 3 tasks

1. Write ingestion/chunker.py + ingestion/verification.py together
2. Run harvester.py against live URLs, verify all 15 docs download
3. Write db/client.py (psycopg3 connection pool + helper functions)

## Module status

ingestion ✅ db ✅ rag ⏳ api ⏳ eval ⏳ frontend ⏳

## Ingestion verification (last run: never)

download — extraction — chunking — embedding —

## RAGAs (last run: never)

faithfulness — relevancy — precision — recall —

## Docs

15 active · 0 superseded · 0 overdue · last harvest 2026-06-01

## Decisions

- Local Postgres 18 + pgvector for dev; Supabase or RDS for production deploy
- psycopg3 (direct driver) over Supabase SDK — no vendor lock-in, portable to any Postgres host
- Docker Compose for local Postgres + pgvector (pgvector/pgvector:pg17 image)
- FastAPI over Flask (async support, auto OpenAPI docs)
- Vite + React over Next.js (simpler for MVP, deploys free on Vercel)
- Chroma locally during dev, migrate to pgvector for production
- Claude API for embeddings and generation (single vendor, BAA path)
- Dallas + Fort Worth use amlegal not Municode (codelibrary.amlegal.com)
- Plano, McKinney, Frisco confirmed on Municode
- up.codes added for Fort Worth amendment tracking
- Citations must reference publisher + date, never imply direct city authority
- verification.py runs at every ingestion stage — no silent failures
- Scanned PDFs flagged as needs_ocr, not ingested until OCR run
- Verification results written to registry.json per document
