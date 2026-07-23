-- db/migrations/025_project_delete_audit_log.sql
-- Audit trail for project soft-delete / restore / hard-delete actions,
-- primarily for superadmin actions taken on projects they don't own
-- (see docs/cognito_groups_rbac.md). No FK on project_id: hard_delete
-- removes the projects row, so the id + a name snapshot must survive it,
-- mirroring purge_audit_log's doc_id pattern.

CREATE TABLE IF NOT EXISTS project_delete_audit_log (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      uuid NOT NULL,
    project_name    text NOT NULL,
    owner_user_id   uuid,
    actor_user_id   uuid NOT NULL,
    actor_username  text NOT NULL,
    actor_role      text NOT NULL,
    action          text NOT NULL CHECK (action IN ('soft_delete', 'hard_delete', 'restore')),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_delete_audit_log_project_id
    ON project_delete_audit_log (project_id);

CREATE INDEX IF NOT EXISTS idx_project_delete_audit_log_created_at
    ON project_delete_audit_log (created_at DESC);
