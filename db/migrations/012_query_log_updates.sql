-- db/migrations/012_query_log_updates.sql
-- Adds: user_id and project_id to query_log, uploaded_by to documents

-- ─── Alter query_log ───────────────────────────────────────────
ALTER TABLE query_log 
    ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_query_log_user ON query_log (user_id) WHERE user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_query_log_project ON query_log (project_id) WHERE project_id IS NOT NULL;

-- ─── Alter documents ───────────────────────────────────────────
ALTER TABLE documents 
    ADD COLUMN IF NOT EXISTS uploaded_by uuid REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents (uploaded_by) WHERE uploaded_by IS NOT NULL;
