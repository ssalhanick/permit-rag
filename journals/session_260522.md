# Session: 2026-05-22

## Type

Foundation session — db client, chunker, verification, first harvest.

## Goal

Complete STATE.md task queue: write db/client.py, ingestion/chunker.py
+ ingestion/verification.py, run harvester against live URLs.

---

## Completed

### db/client.py written

- psycopg3 ConnectionPool (min=1, max=5) with dict_row factory
- Module-level singleton pool via get_pool() / close_pool()
- Context manager get_conn() for connection checkout
- CRUD helpers for all 4 schema tables:
  - insert_document (upsert on doc_id conflict)
  - get_document_by_doc_id, get_document_by_uuid, list_documents
  - insert_chunks (bulk upsert on document_id + chunk_index)
  - delete_chunks_for_document, get_chunks_for_document, count_chunks
  - insert_verification, get_verifications
  - insert_query_log
  - ping() health check
- All functions use type hints, docstrings, proper logging

### ingestion/chunker.py written

- Text extraction: pypdf for PDFs, BeautifulSoup for HTML
- Scanned PDF detection (< 200 chars extracted → needs_ocr)
- Text cleaning: whitespace normalization, boilerplate stripping
- RecursiveCharacterTextSplitter: 1500 chars, 200 overlap
- Split hierarchy tuned for legal text (section → paragraph → sentence)
- CLI entry point for single-document testing
- Tested on Dallas charter: 218 chunks, 250K chars, clean extraction

### ingestion/verification.py written

- 4 verification stages: download, extraction, chunking, embedding
- VerificationResult class with pass/fail/skip/needs_ocr states
- Thresholds: min 500 bytes (download), min 100 chars (extraction),
  80% coverage ratio (chunking)
- Persists results to JSON sidecars (documents/metadata/)
- Persists results to database (ingestion_verifications table)
- run_full_verification() runs all stages, stops at first failure
- print_verification_summary() for human-readable console output

### Harvester run against live URLs

- 9 documents downloaded automatically
- 8 failed (bot protection: amlegal, dallascityhall, OSHA, TDLR, TSBPE)
- Dallas docs manually exported from amlegal as PDF (4 files):
  city-of-dallas-charter.pdf (425 KB),
  city-of-dallas-ordiance-v1.pdf (4.0 MB),
  city-of-dallas-ordiance-v2.pdf (4.3 MB),
  city-of-dallas-ordiance-v3.pdf (13.3 MB)
- Total: 13 documents in registry (9 automated + 4 manual)

### Bug fixes

- harvester.py: fortworth-upcodes-building missing required fields
  (municipality, authority_level, doc_type, subject_tags) + missing
  trailing comma — caused SyntaxError
- harvester.py: load_registry() crashed on empty registry.json
  (JSONDecodeError) — added empty-content guard
- harvester.py: dallas-fee-schedule doc_type was "fee_schedule"
  which doesn't exist in schema enum — changed to "other"
- pyproject.toml: hatchling couldn't find packages — added
  [tool.hatch.build.targets.wheel] packages list

### README.md rewritten

- Updated all commands from dfw_doc_harvester.py → py -m ingestion.harvester
- Added chunking strategy section with parameters, pipeline, optimization plan
- Updated project structure to reflect current layout
- Added architecture decisions section

---

## Files changed

- db/client.py (written — psycopg3 pool + helpers)
- ingestion/chunker.py (written — extraction + chunking)
- ingestion/verification.py (written — 4-stage verification)
- ingestion/harvester.py (bug fixes: missing fields, empty registry, enum)
- pyproject.toml (added hatch build targets)
- README.md (full rewrite)
- STATE.md (updated — tasks advanced, new decisions)
- scripts/test_chunker.py (created — one-off test)
- .gitignore (already had .venv/)

## Files NOT changed

- db/schema.sql (no changes needed)
- docker-compose.yml (not tested yet)
- ingestion/embedder.py (still empty — next session)
- rag/ (not started)

---

## Decisions made

- Chunking: 1500 chars / 200 overlap via RecursiveCharacterTextSplitter
- Dallas amlegal requires manual PDF export (bot protection)
- Dallas code split into 4 documents (charter + 3 ordinance volumes)
- Chunk size will be empirically tuned via RAGAs ablation in Week 4–5
- doc_type "fee_schedule" not in schema enum — used "other" for now

---

## Next session should

1. Stand up Docker Compose and verify db/client.py against live Postgres
2. Run chunker + verification across all 13 documents
3. Write ingestion/embedder.py (Voyage-3 via Anthropic)
4. Remaining failed harvests: try manual download for OSHA, HVAC, plumbing, Frisco UDC

## Prompt for next session

Read STATE.md and journals/session_260522.md. Stand up Docker Compose
(docker compose up -d), verify db/client.py connects and ping() works.
Then run chunker + verification across all 13 docs. If DB works, write
ingestion/embedder.py for Voyage-3 embeddings.
