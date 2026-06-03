-- Migration 003: Add status column to chunks table
-- Purpose: Allows individual chunks to be superseded independently of their
--          parent document (Task 3 / Sprint 1)
-- Run: psql $DATABASE_URL -f db/migrations/003_chunk_status.sql

ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS status document_status NOT NULL DEFAULT 'active';

CREATE INDEX IF NOT EXISTS idx_chunks_status ON chunks (status);

COMMENT ON COLUMN chunks.status IS
    'Lifecycle status of this chunk. Reuses document_status enum. '
    'active = in retrieval pool; superseded = excluded from retrieval '
    'but retained for history.';
