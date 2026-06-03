-- Migration 004: Add source_tier to documents table
-- Purpose: Tracks whether a document is corpus (Tier 1), user ordinance upload
--          (Tier 2), or user project document (Tier 3). Enables corpus-first
--          retrieval ordering and provenance weighting (Task 5 / Sprint 1).
-- Run: psql $DATABASE_URL -f db/migrations/004_source_tier.sql

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS source_tier INTEGER NOT NULL DEFAULT 1
        CONSTRAINT chk_source_tier CHECK (source_tier IN (1, 2, 3));

-- Backfill: all existing documents are corpus documents
UPDATE documents SET source_tier = 1 WHERE source_tier IS NULL;

CREATE INDEX IF NOT EXISTS idx_documents_source_tier ON documents (source_tier);

COMMENT ON COLUMN documents.source_tier IS
    '1 = corpus (scraped, authoritative); '
    '2 = user-uploaded ordinance PDF (supplementary); '
    '3 = user project document (drawings/specs — project context only).';
