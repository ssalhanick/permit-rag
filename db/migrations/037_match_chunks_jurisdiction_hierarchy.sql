-- db/migrations/037_match_chunks_jurisdiction_hierarchy.sql
-- Jurisdiction hierarchy in retrieval — local/state/federal roll-up.
-- ─────────────────────────────────────────────────────────
-- jurisdictions.parent_id (city -> county -> state -> federal) has existed
-- since Sprint 5 but was never walked in application code: match_chunks did a
-- strict equality filter on a single municipality string, so a city-scoped
-- query excluded county/state/federal documents rather than including them
-- alongside. filter_municipality becomes a jurisdiction chain (text[]) —
-- db/client.py's new get_jurisdiction_chain() computes it, e.g. "dallas" ->
-- ARRAY['dallas','dallas-county','texas','federal'].
--
-- This CHANGES the 3rd parameter's type (text -> text[]), not just its
-- default, so it cannot be a bare CREATE OR REPLACE (Postgres would create a
-- second, ambiguous overload rather than replacing the existing one — exactly
-- the "function match_chunks(...) is not unique" failure this repo already
-- hit once, per scripts/fix_match_chunks_overload.py). DROP the old 3-arg
-- (vector, integer, text) signature first, then CREATE the new one.
--
-- ⚠ Deploy-ordering hazard (unlike migration 031's careful same-shape change):
-- this DOES change the call signature, so old application code passing a bare
-- string for filter_municipality will fail once this migration lands but
-- before the app redeploys with db/client.py's updated wrapper. Apply this
-- migration and deploy the matching app code together, not asynchronously.
--
-- ⚠ match_chunks is retrieval-critical: RAGAs MUST be re-run immediately after
--   applying this (AGENTS.md: never change retrieval without RAGAs immediately
--   after; migration 031 flagged the same rule). Do not proceed past this
--   migration in the runbook without that RAGAs run confirming no faithfulness/
--   relevancy/context-precision regression.

DROP FUNCTION IF EXISTS match_chunks(vector, integer, text);

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding      vector(768),
    match_count          int DEFAULT 5,
    filter_municipality  text[] DEFAULT NULL
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
        c.id, c.document_id, d.doc_id, c.content, c.chunk_index,
        d.municipality, d.authority_level, d.doc_type, d.document_status,
        c.status AS chunk_status, d.source_tier, d.ingested_at,
        d.retrieval_weight,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    WHERE d.document_status = 'active'
      AND d.is_current = true
      AND c.status = 'active'
      AND d.content_class = 'authority'      -- transcripts never ground compliance (031)
      AND (filter_municipality IS NULL OR d.municipality = ANY(filter_municipality))
    ORDER BY
        d.source_tier ASC,
        c.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- match_how_to_chunks is untouched: how-to content is a single, national,
-- non-authoritative class (never grounds compliance), so it has no jurisdiction
-- hierarchy concern and keeps its original (vector, integer, text) signature.
