-- Migration 002: Add content_hash to chunks table
-- Purpose: Enables change detection at re-ingest time (Task 2 / Sprint 1)
-- Run: psql $DATABASE_URL -f db/migrations/002_chunk_content_hash.sql

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_hash TEXT;

CREATE INDEX IF NOT EXISTS idx_chunks_content_hash ON chunks (content_hash);

COMMENT ON COLUMN chunks.content_hash IS
    'SHA-256 hex digest of chunk content. Populated at embed time. '
    'Used by re-ingest pipeline to detect changed chunks.';
