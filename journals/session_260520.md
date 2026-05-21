# Session: 2026-05-20

## Type

Correction and research session — no new features built.
Source URLs audited, two wrong entries fixed, one new source added,
ingestion verification system designed.

## Goal

Verify all document source URLs in harvester.py are correct
and pointing to authoritative publishers. Design verification
strategy for ingestion pipeline integrity.

---

## Completed

### Source URL Audit

Discovered Dallas and Fort Worth are NOT on Municode.
DFW cities split across two publishers:

| City        | Publisher                    | Status               |
| ----------- | ---------------------------- | -------------------- |
| Dallas      | American Legal (amlegal)     | ✅ fixed             |
| Fort Worth  | American Legal (amlegal)     | ✅ fixed             |
| Plano       | Municode                     | ✅ confirmed correct |
| McKinney    | Municode                     | ✅ confirmed correct |
| Frisco (TX) | Municode via friscotexas.gov | ✅ confirmed correct |

### Corrections Made to harvester.py catalog

- Replaced `dallas-municode-zoning` with `dallas-amlegal-code`
  URL: codelibrary.amlegal.com/codes/dallas/latest/dallas_tx/0-0-0-1
- Replaced `fortworth-municode-zoning` with `fortworth-amlegal-code`
  URL: codelibrary.amlegal.com/codes/ftworth/latest/ftworth_tx/0-0-0-1

### New Source Added

- Added `fortworth-upcodes-building` from up.codes/codes/fort-worth
  Tracks Fort Worth building code amendments with ordinance numbers
  and effective dates — maps cleanly to metadata schema
  review_days: 30 (amendment-heavy source)

### Important Caveat Documented

Both amlegal and Municode are secondary publishers — they lag
behind actual city council adoptions by days to weeks. Must be
reflected in every citation answer: "per [publisher] as of [date]"
not "per City of Dallas." Review cycles tightened to 60 days
for all amlegal sources.

### Ingestion Verification System Designed

Four-stage verification pipeline to catch silent failures
at every step of the ingestion process:

| Stage      | What it checks                          | Method                 |
| ---------- | --------------------------------------- | ---------------------- |
| Download   | Byte count vs Content-Length header     | SHA-256 + size compare |
| Extraction | Pages extracted vs pages in source PDF  | pypdf page count ratio |
| Chunking   | Chars in chunks vs chars in source text | coverage ratio ≥ 0.85  |
| Embedding  | Chunks in pgvector vs chunks produced   | DB row count compare   |

Key decisions:

- verification.py is a standalone module imported by chunker.py
  and embedder.py — neither completes without running its stage
- All four stage results written to registry.json per document
  under a verification block alongside existing metadata
- Scanned PDFs (avg < 100 chars/page) flagged as needs_ocr,
  skipped from embedding until OCR run — not treated as failure
- Extraction threshold: 90% of source pages must be covered
- Chunk coverage threshold: 85% of source chars must be represented
- IngestionVerification dataclass carries all results through pipeline
- STATE.md gets a new "Ingestion verification" line updated after
  every harvest run alongside RAGAs scores

---

## Files changed

- ingestion/harvester.py (3 catalog entries corrected/added)
- STATE.md (added ingestion verification line + new decisions)
- journals/session_2026-05-20.md (this file)

## Files NOT changed

- AGENTS.md (no rule changes)

## Files to create next session

- ingestion/verification.py (write alongside chunker.py)

---

## Decisions made

- amlegal is authoritative for Dallas + Fort Worth
- Municode is authoritative for Plano, McKinney, Frisco
- up.codes added as supplementary source for amendment tracking
- All citation answers must reference publisher + date,
  never imply direct city authority
- amlegal sources get 60-day review cycle (vs 90 for Municode)
- verification.py runs at every ingestion stage — no silent failures
- Scanned PDFs → needs_ocr status, not a pipeline failure
- Verification block written to registry.json per document

---

## Next session should (June 1, week 1)

1. Create GitHub repo, push initial structure
2. Write pyproject.toml and .env.example
3. Create Supabase project (hosted)
4. Write and deploy db/schema.sql
5. Write ingestion/chunker.py and ingestion/verification.py together
6. Run harvester.py against live URLs, verify all 15 docs download
