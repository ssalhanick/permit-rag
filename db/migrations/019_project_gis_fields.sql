-- 019_project_gis_fields.sql
-- Adds coordinates and overlay district columns to projects.

ALTER TABLE projects
    ADD COLUMN latitude              DOUBLE PRECISION,
    ADD COLUMN longitude             DOUBLE PRECISION,
    ADD COLUMN historic_district     TEXT,
    ADD COLUMN conservation_district TEXT;

COMMENT ON COLUMN projects.latitude              IS 'Latitude coordinate of the project address.';
COMMENT ON COLUMN projects.longitude             IS 'Longitude coordinate of the project address.';
COMMENT ON COLUMN projects.historic_district     IS 'Name of the historic district overlay, if applicable.';
COMMENT ON COLUMN projects.conservation_district IS 'Name of the conservation district overlay, if applicable.';
