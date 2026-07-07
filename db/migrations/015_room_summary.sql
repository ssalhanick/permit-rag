-- Migration 015: room scan summary on projects (Sprint 13 / 14 mobile)
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS room_summary jsonb;

COMMENT ON COLUMN projects.room_summary IS 'Derived room capture metrics (JSON schema v1.0 summary only — no raw mesh)';
