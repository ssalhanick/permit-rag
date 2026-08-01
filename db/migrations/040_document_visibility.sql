-- db/migrations/040_document_visibility.sql
-- Visibility for project-specific (tier-3) documents — document-upload plan, Type 2.
-- ─────────────────────────────────────────────────────────
-- Lets a project member upload a document visible only to themselves
-- ('private') or to the whole project team ('team', the default). Only
-- meaningful for source_tier=3 rows with a project_id — tier-1 (corpus) and
-- tier-2 (pending ordinance) documents get the harmless default and ignore
-- the column, so no CHECK ties it to source_tier: those tiers simply never
-- read it.
--
-- All-DDL, one transaction (apply_migration.py commits the whole file
-- together) -- not idempotent (CREATE TYPE has no IF NOT EXISTS in
-- Postgres), matching 038_overlays.sql's precedent for a new enum column. A
-- second run fails cleanly on CREATE TYPE with no partial state, since the
-- whole file is one transaction.

CREATE TYPE document_visibility AS ENUM ('private', 'team');

ALTER TABLE documents
    ADD COLUMN visibility document_visibility NOT NULL DEFAULT 'team';

CREATE INDEX idx_documents_visibility ON documents (visibility) WHERE source_tier = 3;

COMMENT ON COLUMN documents.visibility IS
    'private (uploader only) or team (whole project team) -- only meaningful '
    'when source_tier=3 AND project_id IS NOT NULL. Retrieval for project docs '
    'must filter visibility=''team'' OR uploaded_by=<querying user>.';
