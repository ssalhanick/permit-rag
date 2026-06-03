-- db/init/02_roles.sql — Docker dev Postgres role setup
-- =======================================================
-- Creates two least-privilege roles for the Docker dev environment.
-- This file is placed in ./db/init/ and mounted into the container at
-- /docker-entrypoint-initdb.d/ — Postgres runs it automatically on first boot.
--
-- corpus_writer: ingestion pipeline (harvester, chunker, embedder)
-- app_reader   : FastAPI application layer (retrieval, answer generation)
--
-- NOTE — Supabase migration path:
--   When moving to Supabase, these Postgres roles are replaced by Row Level
--   Security (RLS) policies. The service_role key (equivalent to corpus_writer)
--   bypasses RLS for writes; authenticated/anon roles (equivalent to app_reader)
--   are restricted to SELECT via RLS policies. Draft those policies in
--   db/supabase_rls.sql before the Supabase cutover sprint.
--
-- Passwords are placeholders — rotate before any shared/cloud deployment.
-- See README for the admin token rotation policy.

-- ── corpus_writer: write access for ingestion pipeline ─────
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'corpus_writer') THEN
        CREATE ROLE corpus_writer LOGIN PASSWORD 'changeme_rotate_corpus';
    END IF;
END
$$;

GRANT INSERT, UPDATE ON
    documents, chunks, ingestion_verifications
TO corpus_writer;

-- corpus_writer also needs to read documents to check hashes and IDs
GRANT SELECT ON documents, chunks TO corpus_writer;

-- sequence access for uuid generation (if using serial fallback)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO corpus_writer;

-- ── app_reader: read-only access for the API ───────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_reader') THEN
        CREATE ROLE app_reader LOGIN PASSWORD 'changeme_rotate_reader';
    END IF;
END
$$;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_reader;

-- Allow app_reader to write the query audit log (structured audit trail)
GRANT INSERT ON query_log TO app_reader;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_reader;
