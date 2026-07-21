-- 022_source_identity.sql
-- On-demand URL pull (docs/on_demand_url_pull.md): document identity keys.
-- Additive only — does not modify any deployed migration.
--
-- Backfill of source_url_normalized / source_filename is done by
-- scripts/backfill_source_identity.py (uses the shared Python normalizer).

ALTER TABLE documents
    ADD COLUMN source_url_normalized TEXT,
    ADD COLUMN source_filename       TEXT,
    ADD COLUMN url_changed_flag      BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN last_pulled_at        TIMESTAMPTZ;

COMMENT ON COLUMN documents.source_url_normalized IS 'Primary identity key: normalized source URL (ingestion/url_normalize.py).';
COMMENT ON COLUMN documents.source_filename       IS 'Fallback identity key: normalized base filename.';
COMMENT ON COLUMN documents.url_changed_flag      IS 'True when identity matched by fallback (URL moved) — needs human review.';
COMMENT ON COLUMN documents.last_pulled_at        IS 'Timestamp of the last on-demand pull that touched this document.';

CREATE INDEX idx_documents_source_url_norm
    ON documents (source_url_normalized);

CREATE INDEX idx_documents_fallback
    ON documents (municipality, doc_type, source_filename);
