-- db/migrations/024_global_roles.sql
-- Cognito groups become the source of truth for global staff roles.
-- Expands users.role to add 'superadmin' alongside existing 'admin' | 'member'.
-- See docs/cognito_groups_rbac.md for the full rollout plan.

ALTER TABLE users DROP CONSTRAINT chk_user_role;
ALTER TABLE users ADD CONSTRAINT chk_user_role CHECK (role in ('member', 'admin', 'superadmin'));

-- Tracks when role was last synced from a Cognito token, for ops visibility.
ALTER TABLE users ADD COLUMN role_synced_at timestamptz NULL;
