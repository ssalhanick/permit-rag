-- Migration 006: Create jurisdictions table
-- Purpose: Stores governing authorities with hierarchy (city → county → state → federal).
--          The `id` column matches the `municipality` string in documents table exactly,
--          enabling FK-style lookups without a translation layer.
--          County + state rows exist now for future GIS resolution (Tasks 14-15).
-- Run: Get-Content db/migrations/006_jurisdictions.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag

CREATE TABLE IF NOT EXISTS jurisdictions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    level       TEXT NOT NULL CHECK (level IN ('federal', 'state', 'county', 'city', 'district')),
    parent_id   TEXT REFERENCES jurisdictions(id),
    dept_name   TEXT,                       -- e.g. 'Dallas Development Services'
    dept_url    TEXT,                       -- building dept permit portal URL
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jurisdictions_level    ON jurisdictions (level);
CREATE INDEX IF NOT EXISTS idx_jurisdictions_parent   ON jurisdictions (parent_id);

COMMENT ON TABLE jurisdictions IS
    'Governing authorities. id matches documents.municipality exactly. '
    'Hierarchy: federal → state → county → city → district. '
    'County/state rows are stubs for GIS resolution (Tasks 14-15).';

COMMENT ON COLUMN jurisdictions.dept_url IS
    'Building department permit portal URL. Populated for city-level rows only. '
    'Replaces static _AHJ_DEPT_URLS dict in api/routes/query.py.';
