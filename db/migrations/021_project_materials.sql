-- Add materials JSONB array to projects
ALTER TABLE projects ADD COLUMN IF NOT EXISTS materials JSONB;
