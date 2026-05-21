# permit_rag — State

_Updated: 2026-05-20_

## Phase

Week 1 of 9 — Foundation

## Blocked on

Nothing currently

## Next 3 tasks

1. Set up pyproject.toml + .env.example + project scaffold
2. Deploy db/schema.sql to Supabase (local dev first)
3. Write ingestion/chunker.py + ingestion/verification.py together

## Module status

ingestion ✅ db ⏳ rag ⏳ api ⏳ eval ⏳ frontend ⏳

## Ingestion verification (last run: never)

download — extraction — chunking — embedding —

## RAGAs (last run: never)

faithfulness — relevancy — precision — recall —

## Docs

15 active · 0 superseded · 0 overdue · last harvest 2026-06-01

## Decisions

- Supabase + pgvector over Pinecone (BAA-eligible, cheaper at MVP scale)
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
