-- Split the overloaded projects.is_active flag into two purpose-built columns:
-- is_archived (ongoing/archived filter tag, non-destructive) and deleted_at
-- (soft delete, hides project behind a restorable trash view).
ALTER TABLE projects ADD COLUMN is_archived boolean NOT NULL DEFAULT false;
UPDATE projects SET is_archived = NOT is_active;
ALTER TABLE projects ADD COLUMN deleted_at timestamptz NULL;
ALTER TABLE projects DROP COLUMN is_active;
DROP INDEX IF EXISTS idx_projects_active;
CREATE INDEX idx_projects_archived ON projects (is_archived);
CREATE INDEX idx_projects_deleted_at ON projects (deleted_at) WHERE deleted_at IS NOT NULL;

-- Single "active project" per user account, persisted server-side so the nav
-- project switcher and auto-attach on query/upload survive page reloads.
ALTER TABLE users ADD COLUMN active_project_id uuid NULL
  REFERENCES projects(id) ON DELETE SET NULL;
