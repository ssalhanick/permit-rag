-- db/migrations/013_cognito_auth.sql
-- Migrates users table from custom JWT/Argon2id to Amazon Cognito authentication.
--
-- DESTRUCTIVE: truncates all existing users (pre-production only — no real users).
-- Run order: apply after 012_query_log_updates.sql.

-- ─── Clear all user data (cascades to project_members, sets null on project_documents/query_log) ──
TRUNCATE TABLE users CASCADE;

-- ─── Drop custom auth columns (no longer needed — Cognito owns credentials) ───
ALTER TABLE users DROP COLUMN IF EXISTS password_hash;
ALTER TABLE users DROP COLUMN IF EXISTS refresh_token_hash;
ALTER TABLE users DROP COLUMN IF EXISTS token_family;

-- ─── Add Cognito sub as external identity key ───────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS cognito_sub TEXT UNIQUE;

CREATE INDEX IF NOT EXISTS idx_users_cognito_sub ON users (cognito_sub);
