-- db/migrations/031_media_transcripts.sql
-- Media Curator Slice C1 — segregated how-to video transcripts.
-- ─────────────────────────────────────────────────────────
-- DIY how-to queries abstain against a permit-code corpus (nothing clears the
-- grounding floor). This lets the vetted media_refs videos' transcripts be
-- ingested and retrieved — but as a SEGREGATED, NON-AUTHORITATIVE class that
-- never grounds or cites a compliance answer. Owner decision (2026-07-25):
-- "separate tier, never grounds compliance", so faithfulness (>=0.85) is untouched.
--
-- Mechanism: a `content_class` column ('authority' | 'how_to'). match_chunks
-- gains a `filter_content_class` param DEFAULTING to 'authority', so the existing
-- compliance retrieval path is byte-for-byte unchanged — every existing document
-- is 'authority' by the column default. A how-to retrieval passes 'how_to'.
--
-- ⚠ match_chunks is retrieval-critical: RAGAs MUST be re-run after applying this
--   (AGENTS.md: never change retrieval without RAGAs immediately after). The
--   default-'authority' filter is designed to keep the number identical.
--
-- Requires Postgres 12+ for `ALTER TYPE ... ADD VALUE` inside a transaction
-- (schema targets PG15). The new values are only ADDED here, never USED in this
-- same transaction (the ingest script inserts transcript rows later), so the
-- "unsafe use of new value" restriction does not apply. Additive/idempotent.

-- 1. Honest metadata values for a non-government, educational source.
ALTER TYPE authority_level ADD VALUE IF NOT EXISTS 'educational';
ALTER TYPE doc_type        ADD VALUE IF NOT EXISTS 'how_to_video';

-- 2. The segregation marker. Default 'authority' = every existing corpus doc.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS content_class text NOT NULL DEFAULT 'authority';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'documents_content_class_chk'
    ) THEN
        ALTER TABLE documents
            ADD CONSTRAINT documents_content_class_chk
            CHECK (content_class IN ('authority', 'how_to'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_documents_content_class
    ON documents (content_class);

COMMENT ON COLUMN documents.content_class IS
    'Retrieval segregation: authority (permit code, grounds compliance) vs how_to '
    '(video transcripts, DIY-only, never grounds or cites a compliance answer). '
    'match_chunks filters on this, defaulting to authority.';

-- 3. match_chunks gains the content_class filter. Adding a parameter changes the
--    signature, so drop the old 3-arg version first (avoids overload ambiguity).
--    The return table is UNCHANGED — only the WHERE clause and the new param.
DROP FUNCTION IF EXISTS match_chunks(vector, integer, text);

CREATE FUNCTION match_chunks(
    query_embedding      vector(768),
    match_count          int default 5,
    filter_municipality  text default null,
    filter_content_class text default 'authority'
)
returns table (
    id              uuid,
    document_id     uuid,
    doc_id          text,
    content         text,
    chunk_index     integer,
    municipality    text,
    authority_level authority_level,
    doc_type        doc_type,
    document_status document_status,
    chunk_status    document_status,
    source_tier     integer,
    ingested_at     timestamptz,
    retrieval_weight numeric,
    similarity      float
)
language sql stable
as $$
    select
        c.id,
        c.document_id,
        d.doc_id,
        c.content,
        c.chunk_index,
        d.municipality,
        d.authority_level,
        d.doc_type,
        d.document_status,
        c.status          as chunk_status,
        d.source_tier,
        d.ingested_at,
        d.retrieval_weight,
        1 - (c.embedding <=> query_embedding) as similarity
    from chunks c
    join documents d on d.id = c.document_id
    where d.document_status = 'active'
      and d.is_current = true
      and c.status = 'active'
      and (filter_municipality is null or d.municipality = filter_municipality)
      and (filter_content_class is null or d.content_class = filter_content_class)
    order by
        d.source_tier asc,
        c.embedding <=> query_embedding
    limit match_count;
$$;
