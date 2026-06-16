-- Migration 010 — Fix match_chunks() ORDER BY (Sprint 5 / Fix 1)
-- ---------------------------------------------------------------
-- Problem: ordering by source_tier ASC before cosine distance means
-- a weak Tier-1 chunk (sim=0.35) beats a relevant Tier-2 chunk
-- (sim=0.90) before the Python reranker ever sees it.
--
-- Fix: order purely by cosine distance; the provenance reranker in
-- rag/reranker.py already applies tier_factor as a multiplier and
-- is the correct place for tier bias.
--
-- Run against Docker dev DB:
--   Get-Content db/migrations/010_fix_match_chunks_ordering.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding     vector(768),
    match_count         int     DEFAULT 5,
    filter_municipality text    DEFAULT null
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
LANGUAGE sql STABLE AS $$
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
        c.embedding <=> query_embedding   -- pure cosine; tier handled by Python reranker
    LIMIT match_count;
$$;
