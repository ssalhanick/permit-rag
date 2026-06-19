-- Migration 008: Pilot municipal boundaries table + first city geometry
-- Run:
--   Get-Content db/migrations/008_municipal_boundaries_pilot.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag

CREATE TABLE IF NOT EXISTS municipal_boundaries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdictions(id),
    boundary_name   TEXT NOT NULL,
    source_name     TEXT NOT NULL,
    source_url      TEXT,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (jurisdiction_id)
);

CREATE INDEX IF NOT EXISTS idx_municipal_boundaries_jurisdiction
    ON municipal_boundaries (jurisdiction_id);

CREATE INDEX IF NOT EXISTS idx_municipal_boundaries_geom
    ON municipal_boundaries
    USING GIST (geom);


