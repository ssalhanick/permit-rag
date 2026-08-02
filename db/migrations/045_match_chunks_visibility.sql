-- db/migrations/045_match_chunks_visibility.sql
-- Close the tier-3 document visibility gap in match_chunks retrieval.
-- ─────────────────────────────────────────────────────────
-- migration 040 added documents.visibility ('private'/'team') with the
-- documented intent that retrieval "must filter visibility='team' OR
-- uploaded_by=<querying user>" -- but match_chunks (037) never implemented
-- that filter. match_chunks has no source_tier restriction in its WHERE
-- clause at all, so a tier-3 project document -- including one explicitly
-- marked 'private' -- was reachable by the general corpus search for ANY
-- user asking about that municipality, not just the uploader or their
-- project teammates. Confirmed: a private document's content could surface
-- verbatim in another user's chat answer.
--
-- The application-level plumbing for this was already mostly built:
-- api/routes/query.py -> manager.py -> retrieve_with_project() already
-- thread a requesting_user_id end to end for exactly this purpose (see
-- retrieve_with_project's own docstring in rag/retriever.py) -- it just
-- never made the last two hops (retrieve() -> match_chunks()). This
-- migration plus the matching db/client.py + rag/retriever.py changes
-- finish that wiring; no route or Manager change needed.
--
-- Deliberately narrow: only tier-3 rows are affected. Tier-1 (shared
-- jurisdiction corpus) and tier-2 (pending ordinance petitions) never read
-- the visibility column -- see 040's own header -- so they are explicitly
-- exempted (`source_tier <> 3`) rather than newly gated by a column that was
-- never meant to apply to them.
--
-- This is a signature change (new 4th parameter), so it cannot be a bare
-- CREATE OR REPLACE -- same "not unique" overload hazard 037 already
-- documented. DROP the current 3-arg signature first, then CREATE the new
-- 4-arg one.
--
-- Deploy-ordering hazard (same as 037): apply this migration and deploy the
-- matching app code (db/client.py's updated match_chunks() wrapper) together,
-- not asynchronously -- old app code calling the 3-arg signature will fail
-- once this lands but before the app redeploys.
--
-- match_chunks is retrieval-critical: RAGAs MUST be re-run immediately after
-- applying this (AGENTS.md RAG Quality Rules; migrations 031/037 flagged the
-- same rule). This machine (repo/machine A) has no corpus -- ships
-- code-complete here, RAGAs run happens on the corpus machine. Do not treat
-- this as verified until that run confirms no faithfulness/relevancy/context
-- precision regression vs. the pre-045 baseline.

DROP FUNCTION IF EXISTS match_chunks(vector, integer, text[]);

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding      vector(768),
    match_count          int DEFAULT 5,
    filter_municipality  text[] DEFAULT NULL,
    requesting_user_id   uuid DEFAULT NULL
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
      AND (
          d.source_tier <> 3                                 -- tier 1/2 unaffected (040)
          OR d.visibility = 'team'                            -- 040's documented default: team = broadly visible
          OR d.uploaded_by = requesting_user_id                -- private doc's own uploader
      )
    ORDER BY
        d.source_tier ASC,
        c.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- match_how_to_chunks and match_project_chunks are untouched: how-to content
-- has no tier-3 visibility concern (031), and match_project_chunks already
-- takes and uses requesting_user_id for this exact purpose (040) -- this
-- migration closes the *other* gap, the general corpus path.
