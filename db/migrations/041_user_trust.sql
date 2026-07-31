-- db/migrations/041_user_trust.sql
-- Tiered trust for jurisdiction ordinance petitions — document-upload plan, Type 1.
-- ─────────────────────────────────────────────────────────
-- A verified contributor's ordinance petition is auto-approved straight into
-- the shared corpus (source_tier=1); everyone else's lands in a pending
-- queue (source_tier=2) for staff review. This is a lightweight per-user
-- flag, deliberately NOT layered onto users.role (member/admin/superadmin,
-- migration 024) -- that column is the staff/ops permission axis
-- (docs/cognito_groups_rbac.md), orthogonal to "has this member earned
-- auto-approval for ordinance uploads." Admin-settable by the same
-- is_staff()/is_superadmin() gate api/auth.py already applies elsewhere
-- (e.g. api/routes/overlays.py's admin endpoints).
--
-- Additive and idempotent (ADD COLUMN IF NOT EXISTS, plain boolean -- no new
-- enum type, unlike 040_document_visibility.sql).

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_verified_contributor boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN users.is_verified_contributor IS
    'Staff-granted trust flag. An ordinance petition (POST /documents/petitions) '
    'from a verified contributor skips the pending queue and goes straight to '
    'source_tier=1/document_status=active, same as the admin upload path.';
