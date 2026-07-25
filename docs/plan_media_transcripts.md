# Plan — Video transcript ingest + retrieval (Media Curator Slice C)

_Drafted 2026-07-25. Follows Media Curator B1 (curated links)._

> **Status (2026-07-25): C1 BUILT** (machine-A compile + transcript smoke green) —
> migration 031 (**non-breaking**: `match_chunks` keeps its 3-arg signature, body
> scoped to `content_class='authority'` in SQL; new `match_how_to_chunks` for the
> diy path — so migration/deploy need no ordering), `db.client`
> (`match_chunks` unchanged sig + `match_how_to_chunks` + `insert_document`
> content_class + `list_media_refs`), `ingestion/transcript.py`,
> `scripts/ingest_media_transcripts.py`, `pyproject` dep, `tests/test_transcript.py`.
> **Verify on machine B** (install dep → apply 031 → ingest → **RAGAs**) before
> **C2** (the how-to answer wiring below) is built.

## Goal

Make DIY how-to queries **answerable** instead of abstaining. Today the corpus is
permit *code*, so "how do I install a GFCI outlet" retrieves nothing above the
grounding floor → abstain. This slice ingests the transcripts of the vetted
`media_refs` videos, embeds them locally (`nomic-embed-text-v1.5`), and stores
them as a **segregated, non-authoritative** retrieval class so a diy query can be
grounded on how-to content **without ever letting video text ground or cite a
compliance answer**.

## The governing decision (owner, 2026-07-25)

**Separate tier, never grounds compliance.** Transcript docs live in
`documents`/`chunks` (reusing the pipeline) but are marked non-authoritative and
are **excluded from compliance retrieval and the compliance grounding floor**.
They are retrieved only on the diy/how-to path, and never cited as permit
authority. Compliance faithfulness (≥0.85) is therefore untouched.

## Reuses what exists

- `ingestion/chunker.py` — same chunking.
- `ingestion/embedder.py` — `nomic-embed-text-v1.5`, 768-dim, **local, no API cost**.
- `documents`/`chunks` + `match_chunks` — same store; a filter keeps the classes apart.
- `scripts/ingest_prod_corpus.py` pattern — **embed locally on machine B, push to
  prod RDS** (`ENVIRONMENT=production`). This is exactly the owner's intended flow.

## New parts

### Slice C1 — ingest + segregation (the foundation)

**1. Migration `031_media_transcripts.sql`** (031; B1 took 030; Phase-6 ontology → 032)
- Enum adds (run with autocommit — `ALTER TYPE … ADD VALUE` can't be used in the
  same transaction it's added in): `authority_level += 'educational'`,
  `doc_type += 'how_to_video'`. `IF NOT EXISTS`, idempotent.
- `ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_class text NOT NULL
  DEFAULT 'authority'` (+ `CHECK (content_class IN ('authority','how_to'))`) +
  index. This column, not the enums, is what retrieval filters on — cleaner and
  reversible. `source_tier = 3` for transcripts (lowest priority; `match_chunks`
  already orders tier asc).
- **Numbering caveat:** keep the enum `ALTER TYPE` statements in their own file or
  run first with autocommit; `apply_migration.py` behavior with `ADD VALUE` must be
  checked (it may wrap in a transaction).

**2. `ingestion/transcript.py`** — fetch a YouTube transcript.
- New dep: `youtube-transcript-api` (pin in `pyproject.toml`). Given a
  `media_refs.url`, extract the video id, fetch caption segments, join to text.
  No API cost. Missing/disabled captions → skip with a logged reason (not fatal).

**3. `scripts/ingest_media_transcripts.py`** — the driver (target-safe via `_db_target`).
- Read active `media_refs`; for each: fetch transcript → chunk → embed (local) →
  insert `documents` row (`content_class='how_to'`, `doc_type='how_to_video'`,
  `authority_level='educational'`, `source_tier=3`,
  `municipality = jurisdiction or 'national'`, `effective_date=NULL`,
  `checksum_sha256 = sha256(transcript)`, `document_status='active'`) + `chunks` +
  embeddings. Idempotent: dedupe on a stable `doc_id` derived from the video id;
  re-run re-embeds only changed transcripts. Local by default; prod via
  `ENVIRONMENT=production` (the `ingest_prod_corpus` pattern).
- **Metadata-policy note (AGENTS.md "never ingest without full metadata"):**
  transcripts are an explicit, documented exception — `effective_date`/`review_due`
  are NULL by design (a video has no adoption date), `authority_level='educational'`
  records that it is *not* a government source. Written into README "Data Sources &
  Limitations".

**4. Retrieval segregation** — `match_chunks` + `rag/retriever.py`.
- Add an optional `content_class` filter to `match_chunks`, **defaulting to
  `'authority'`** so the existing compliance path is byte-for-byte unchanged (no
  RAGAs movement — but **run RAGAs after**, per AGENTS.md "never change retrieval
  without RAGAs immediately after").
- A how-to retrieval (`content_class='how_to'`) for the diy path.
- Result: transcript chunks never enter compliance retrieval, never count toward
  the compliance grounding floor, never appear as compliance citations.

### Slice C2 — wire the how-to answer (the payoff)

- On the **diy** path, when compliance retrieval abstains (or always, for how_to
  intent), run a **how-to retrieval** over `content_class='how_to'` and generate a
  grounded how-to answer, with the Media Curator's videos attached.
- Distinct **disclaimer**: educational, not authoritative — verify permits with the
  AHJ. Guardrail enforces presence (separate from `_AHJ_DISCLAIMER_TEXT`).
- Citations point to the **video** (title + url), never framed as permit authority.
- The compliance grounding floor / AHJ answer path is unchanged.

## Governance / quality guardrails (AGENTS.md)

- **Faithfulness ≥0.85 untouched:** default retrieval stays authority-only; run
  `ragas_eval` after the `match_chunks` change to prove no movement.
- **Non-authoritative never grounds compliance:** enforced by the `content_class`
  filter, not convention.
- **Full-metadata rule:** transcripts are a documented exception with a defined
  policy (educational / no effective_date), recorded in README + here.
- **Disclaimer enforced** on how-to answers by the Guardrail.

## Acceptance

- C1: `ingest_media_transcripts.py --local` ingests the seeded videos' transcripts;
  a compliance query's retrieval + citations + RAGAs are unchanged (authority-only);
  a `content_class='how_to'` retrieval returns transcript chunks.
- C2: a diy "how do I install a GFCI outlet" returns a grounded how-to answer +
  the video, with the educational disclaimer; the same query as `research`/
  `contractor` is unaffected (no how-to answer, no video).
- Local→prod: re-run under `ENVIRONMENT=production` pushes transcript docs to prod RDS.

## Open questions before C2

- Should how_to retrieval run **only on a compliance abstain**, or **always for
  how_to intent**? (Abstain-triggered is the conservative start.)
- One video ≈ one document, or group by task_key? (Start one-doc-per-video.)
