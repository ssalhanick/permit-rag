-- db/migrations/035_query_log_session_id.sql
-- Query sessions: group multiple questions into one client-tracked thread.
-- ─────────────────────────────────────────────────────────
-- The Query page previously listed one sidebar entry per question, with no
-- way to see a run of follow-ups as a single conversation. `session_id` is a
-- UUID the frontend generates once per "New Compliance Query" click and
-- resends (via the `X-Client-Session-Id` header, already parsed but until now
-- unused for persistence — see `api/routes/query.py`) on every submit until
-- the user starts a new one. The frontend groups `query_log` rows by this
-- column to render a thread instead of a flat list. Display/grouping only —
-- prior turns are not fed into generation as conversational context.
--
-- Nullable, no backfill: rows logged before this column existed have no
-- session and the frontend treats each as its own singleton session, keyed
-- by the row's own id.
--
-- Numbering: 034 is reserved for the (unshipped) Phase 6 ontology/bids
-- cascade per STATE.md's migration-numbering note; this takes 035.

ALTER TABLE query_log ADD COLUMN IF NOT EXISTS session_id uuid;

CREATE INDEX IF NOT EXISTS idx_query_log_user_session
    ON query_log (user_id, session_id, created_at DESC);

COMMENT ON COLUMN query_log.session_id IS
    'Client-generated UUID grouping queries into one chat-style session/thread. '
    'NULL for rows logged before this column existed; the frontend treats those '
    'as singleton sessions keyed by their own row id.';
