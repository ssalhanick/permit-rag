-- 020_project_custom_prompt.sql
-- Adds budget, persona, and custom_system_prompt columns to projects.

ALTER TABLE projects
    ADD COLUMN budget               TEXT,
    ADD COLUMN persona              TEXT,
    ADD COLUMN custom_system_prompt TEXT;

COMMENT ON COLUMN projects.budget               IS 'Estimated budget for the project.';
COMMENT ON COLUMN projects.persona              IS 'User role persona (e.g. diy, hiring_contractor, contractor).';
COMMENT ON COLUMN projects.custom_system_prompt IS 'LLM-synthesized prompt/instructions tailored to the project profile.';
