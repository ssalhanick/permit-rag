-- Migration 009: Add purge audit log table
-- Run:
--   Get-Content db/migrations/009_purge_audit_log.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag

CREATE TABLE IF NOT EXISTS purge_audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id              TEXT NOT NULL,
    document_id         UUID,
    actor_identity      TEXT NOT NULL,
    actor_role          TEXT NOT NULL,
    source_tier         INTEGER NOT NULL CHECK (source_tier IN (1, 2, 3)),
    deleted_chunk_count INTEGER NOT NULL DEFAULT 0,
    local_file_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_purge_audit_log_doc_id
    ON purge_audit_log (doc_id);

CREATE INDEX IF NOT EXISTS idx_purge_audit_log_created_at
    ON purge_audit_log (created_at DESC);
