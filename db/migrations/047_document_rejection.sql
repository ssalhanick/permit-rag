-- db/migrations/047_document_rejection.sql
-- Give rejected ordinance petitions a visible terminal state instead of a
-- silent hard delete.
-- ─────────────────────────────────────────────────────────
-- reject_pending_document (db/client.py) previously deleted the chunks and
-- the documents row outright -- a tier-2 petition just vanished from the
-- submitter's "Documents" library with no explanation. There is no email/
-- notification system anywhere in this codebase, so the fix is to keep the
-- row (submitters already poll GET /api/documents?scope=mine for status)
-- and record why, rather than build a notification channel that doesn't
-- exist yet. This mirrors overlays.status, which already has a 'rejected'
-- value and keeps its row on rejection (db_client.reject_overlay).
--
-- Additive and idempotent. ADD VALUE IF NOT EXISTS is safe to re-run and
-- cannot destroy data. On Postgres 12+ ADD VALUE runs inside a transaction
-- as long as the new label is not *used* in the same transaction -- this
-- migration only declares the label, so apply_migration.py's single-
-- transaction apply is fine (same reasoning as 028_metadata_validation.sql).

ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'rejected';

ALTER TABLE documents ADD COLUMN IF NOT EXISTS rejection_reason text;

COMMENT ON COLUMN documents.rejection_reason IS
    'Set when document_status is rejected (reject_pending_document). Surfaced '
    'to the submitter via GET /api/documents?scope=mine -- the only place a '
    'petitioner sees their own document status today.';
