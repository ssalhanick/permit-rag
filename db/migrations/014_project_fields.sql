-- 014_project_fields.sql
-- Adds address, spaces, work_types, and recommended_permits to projects.
-- All columns are nullable. No existing rows are affected.

ALTER TABLE projects
    ADD COLUMN address              TEXT,
    ADD COLUMN spaces               JSONB,
    ADD COLUMN work_types           JSONB,
    ADD COLUMN recommended_permits  JSONB;

COMMENT ON COLUMN projects.address             IS 'Full civic address gathered during project kickoff.';
COMMENT ON COLUMN projects.spaces              IS 'Array of selected space labels (e.g. ["Kitchen","Roof"]).';
COMMENT ON COLUMN projects.work_types          IS 'Array of selected work-type labels (e.g. ["Plumbing","Electrical"]).';
COMMENT ON COLUMN projects.recommended_permits IS 'Permit categories recommended by rule-based logic at creation time.';
