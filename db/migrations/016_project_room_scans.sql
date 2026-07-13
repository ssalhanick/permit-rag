-- db/migrations/016_project_room_scans.sql
-- Multi-scan room summaries per project (derived metrics only — no surfaces).

CREATE TABLE project_room_scans (
    id               uuid PRIMARY KEY,
    project_id       uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scan_type        text NOT NULL
                         CONSTRAINT chk_scan_type CHECK (scan_type IN ('structure', 'room')),
    parent_scan_id   uuid REFERENCES project_room_scans(id) ON DELETE CASCADE,
    room_label       text NOT NULL,
    section          text,
    captured_at      timestamptz NOT NULL,
    derived          jsonb NOT NULL,
    is_active        boolean NOT NULL DEFAULT false,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_project_room_scans_project
    ON project_room_scans (project_id);

CREATE INDEX idx_project_room_scans_parent
    ON project_room_scans (parent_scan_id)
    WHERE parent_scan_id IS NOT NULL;

CREATE UNIQUE INDEX uq_project_room_scans_active_room
    ON project_room_scans (project_id)
    WHERE is_active = true AND scan_type = 'room';

COMMENT ON TABLE project_room_scans IS
    'Derived room/structure scan summaries synced from mobile (A+C privacy — no mesh).';

CREATE TRIGGER trg_project_room_scans_updated_at
    BEFORE UPDATE ON project_room_scans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
