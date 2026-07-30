-- db/migrations/038_overlays.sql
-- Generalized overlay/petition system — historic/conservation districts, HOAs.
-- ─────────────────────────────────────────────────────────
-- Replaces the Dallas-only, hardcoded pattern (projects.historic_district /
-- conservation_district TEXT columns + flat per-city GeoJSON files in
-- rag/gis.py + db/gis_data/<city>/) with one generic, type-agnostic model:
-- a named overlay with real PostGIS geometry, a petition/approval workflow,
-- and linked source documents. Additive — rag/gis.py and the two existing
-- project columns keep working for Dallas exactly as before; this does not
-- remove or migrate that pilot data.
--
-- Direct implementation of the ask: "the ability to upload any historic or
-- conservation district documentation at the project level... petitioned to
-- be added to the corpus with a tight boundary so it doesn't bleed into
-- non-affected property queries... adjusted for HOA bylaws."

CREATE TYPE overlay_type AS ENUM ('historic_district', 'conservation_district', 'hoa', 'other');
CREATE TYPE overlay_status AS ENUM ('petitioned', 'approved', 'rejected');

CREATE TABLE overlays (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    text NOT NULL,
    overlay_type            overlay_type NOT NULL,
    jurisdiction_id         text REFERENCES jurisdictions(id),
    geom                    geometry(MultiPolygon, 4326),   -- nullable until finalized
    status                  overlay_status NOT NULL DEFAULT 'petitioned',
    petitioned_by           uuid REFERENCES users(id) ON DELETE SET NULL,
    petitioning_project_id  uuid REFERENCES projects(id) ON DELETE SET NULL,
    approved_by             uuid REFERENCES users(id) ON DELETE SET NULL,
    approved_at             timestamptz,
    notes                   text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_overlays_geom ON overlays USING gist (geom);
CREATE INDEX idx_overlays_status ON overlays (status);

CREATE TRIGGER trg_overlays_updated_at
    BEFORE UPDATE ON overlays
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

ALTER TABLE documents ADD COLUMN overlay_id uuid REFERENCES overlays(id) ON DELETE SET NULL;
CREATE INDEX idx_documents_overlay ON documents (overlay_id) WHERE overlay_id IS NOT NULL;

COMMENT ON TABLE overlays IS
    'A named, geometrically-bounded overlay (historic/conservation district, HOA, '
    'or other micro-jurisdiction) petitioned by a project and, once approved, '
    'surfaced to any OTHER project whose address falls inside its geometry -- not '
    'just the petitioning project. geom is nullable: a petition starts with a '
    'coarse default buffer around the petitioning project''s point and can be '
    'refined by staff before/at approval.';
