# Session: 2026-05-25

## Type

Foundation session — Docker setup, DB verification, chunking all docs, embedder module.

## Goal

Complete STATE.md tasks 1–3: stand up Docker Compose, verify db/client.py,
run chunker + verification across all 13 docs, write ingestion/embedder.py.

---

## Completed

### Docker Compose + DB connection verified

- Fixed .env: `postgressql` typo → `postgresql`, removed spaces around `=`
- Discovered local Windows Postgres (postgres.exe) occupying port 5432
- Remapped Docker to port 5433 to avoid conflict
- Fixed pg_hba.conf auth: changed `scram-sha-256` to `md5`/`trust` for Docker gateway IP
- After ALTER USER PASSWORD + pg_hba fix, `ping()` returns True
- psycopg-pool was missing — installed and added to pyproject.toml
- Schema applied successfully: documents, chunks, ingestion_verifications, query_log

### Schema updates

- Added `state_statute` and `federal_regulation` to doc_type enum
  (used by harvester catalog, were missing from schema)
- Changed `vector(1024)` → `vector(768)` in chunks table + match_chunks()
  (nomic-embed-text-v1.5 = 768 dims, not Voyage-3's 1024)
- Updated verification.py dim check from 1024 → 768

### Chunker + verification run across all 13 documents

- 10/13 pass all verification stages (download → extraction → chunking)
- 3 fail at extraction: frisco-municode-zoning, mckinney-municode-zoning,
  plano-municode-zoning (Municode JS redirect pages, ~90 chars extracted)
- Chunk counts for passing docs:
  - city-of-dallas-charter: 218 chunks
  - city-of-dallas-ordiance-v1: 2,111 chunks
  - city-of-dallas-ordiance-v2: 1,890 chunks
  - city-of-dallas-ordiance-v3: 2,931 chunks
  - ada-design-standards: 5 chunks
  - epa-stormwater-construction: 4 chunks
  - fortworth-upcodes-building: 3 chunks
  - plano-building-permit-info: 1 chunk
  - texas-accessibility-standards: 5 chunks
  - texas-contractor-licensing-electrical: 2 chunks
- Total: ~7,169 chunks across 10 documents

### ingestion/embedder.py written (nomic-embed-text-v1.5)

- Local inference via sentence-transformers (no API key, no cost)
- Singleton model loader with GPU/CPU auto-detection
- `embed_texts()`: core embedding with search_document/search_query prefixes
- `embed_query()`: convenience for single search queries
- `embed_document_chunks()`: batch embedding for a document's chunks
- `embed_document()`: full pipeline (load chunks → embed → store → verify)
- `embed_all_documents()`: runs pipeline for all active docs
- `store_embeddings()`: writes vectors to pgvector via db/client.py
- `unload_model()`: frees memory after batch jobs
- CLI: `py ingestion/embedder.py [doc_id] [--dry-run]`

### tests/test_embedder.py written

- All tests mock the model (no real model loading)
- Tests: prefix application, query embedding, content extraction, model unloading

### Design decision: nomic-embed-text over Voyage-3

- No API key required, no per-token cost
- 768-dim vectors (good quality, lower storage than 1024)
- 8192 token context window (enough for 1500-char chunks)
- Supports Matryoshka representations for future dim reduction
- Can run on CPU (slower) or GPU (fast)

### Design decision: hybrid search planned

- Current: dense vector search via pgvector (cosine similarity)
- Future: add BM25 sparse retrieval for hybrid scoring
- No changes to chunker needed — dense models handle raw text
- BM25 index would be a separate addition in rag/pipeline.py

---

## Files changed

- .env (fixed typo, port 5432 → 5433)
- .env.example (removed VOYAGE_API_KEY, updated EMBEDDING_MODEL to nomic)
- db/schema.sql (added enum values, vector(1024) → vector(768))
- docker-compose.yml (port mapping 5432:5432 → 5433:5432)
- pyproject.toml (added psycopg-pool, sentence-transformers; removed voyageai)
- ingestion/embedder.py (written — nomic-embed-text local pipeline)
- ingestion/verification.py (embedding_dim 1024 → 768)
- tests/test_embedder.py (written — mocked unit tests)
- scripts/run_chunk_verify.py (written — schema check + chunk all docs)
- STATE.md (updated)

## Files NOT changed

- db/client.py (no changes needed)
- ingestion/chunker.py (no changes needed)
- ingestion/harvester.py (no changes needed)
- rag/ (not started)

---

## Decisions made

- Docker port 5433 (not 5432) to avoid local Windows Postgres conflict
- nomic-embed-text-v1.5 over Voyage-3 (local, free, no API key)
- sentence-transformers for local inference (not voyageai SDK)
- 768-dim embeddings (nomic default, matches schema)
- No tokenization/lemmatization in chunker — dense models handle semantics
- Hybrid search (dense + BM25) planned for future, architecture kept open
- psycopg-pool is a separate pip package from psycopg[binary]
- Schema needs state_statute + federal_regulation doc_type values

---

## Next session should

1. Install sentence-transformers: `pip install sentence-transformers`
2. Recreate Docker volume: `docker compose down -v && docker compose up -d`
   (schema changed from vector(1024) to vector(768))
3. Write a script to ingest the 10 passing docs into DB (insert_document + insert_chunks)
4. Run embedder on texas-contractor-licensing-electrical (2 chunks) as smoke test
5. If that works, embed all 10 documents
6. Begin rag/pipeline.py — retrieval via match_chunks(), plan hybrid search

## Prompt for next session

Read STATE.md and journals/session_250525.md. Install sentence-transformers,
recreate the Docker volume (schema vector dim changed to 768). Write a script
to ingest the 10 passing documents into the database (insert_document +
insert_chunks from db/client.py). Then run embedder on
texas-contractor-licensing-electrical (2 chunks) as a smoke test. If that
works, embed all 10 documents and verify embedding coverage.
