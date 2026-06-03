-- Migration 005: Update match_chunks() SQL function
-- Adds chunk status filter, source_tier ordering, and new return columns
-- (chunk_status, source_tier, ingested_at, retrieval_weight).
-- Must DROP first — Postgres does not allow changing a function's return type
-- via CREATE OR REPLACE.
-- Run: Get-Content db/migrations/005_match_chunks_update.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag

DROP FUNCTION IF EXISTS match_chunks(vector, integer, text);

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding  vector(768),
    match_count      int default 5,
    filter_municipality text default null
)
RETURNS TABLE (
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
LANGUAGE sql STABLE
AS $$
    SELECT
        c.id,
        c.document_id,
        d.doc_id,
        c.content,
        c.chunk_index,
        d.municipality,
        d.authority_level,
        d.doc_type,
        d.document_status,
        c.status          AS chunk_status,
        d.source_tier,
        d.ingested_at,
        d.retrieval_weight,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.document_status = 'active'
      AND d.is_current = true
      AND c.status = 'active'
      AND (filter_municipality IS NULL OR d.municipality = filter_municipality)
    ORDER BY
        d.source_tier ASC,
        c.embedding <=> query_embedding
    LIMIT match_count;
$$;
