-- db/migrations/017_user_room_scan_library.sql
-- User-owned scan library + optional project links (A+C derived summaries only).

CREATE TABLE user_room_scans (
    id               uuid PRIMARY KEY,
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scan_type        text NOT NULL
                         CONSTRAINT chk_user_scan_type CHECK (scan_type IN ('structure', 'room')),
    parent_scan_id   uuid REFERENCES user_room_scans(id) ON DELETE CASCADE,
    room_label       text NOT NULL,
    section          text,
    structure_label  text,
    captured_at      timestamptz NOT NULL,
    derived          jsonb NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_room_scans_user
    ON user_room_scans (user_id);

CREATE INDEX idx_user_room_scans_parent
    ON user_room_scans (parent_scan_id)
    WHERE parent_scan_id IS NOT NULL;

CREATE TABLE project_room_scan_links (
    project_id  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scan_id     uuid NOT NULL REFERENCES user_room_scans(id) ON DELETE CASCADE,
    is_active   boolean NOT NULL DEFAULT false,
    linked_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, scan_id)
);

CREATE INDEX idx_project_room_scan_links_scan
    ON project_room_scan_links (scan_id);

CREATE UNIQUE INDEX uq_project_room_scan_links_active
    ON project_room_scan_links (project_id)
    WHERE is_active = true;

CREATE TRIGGER trg_user_room_scans_updated_at
    BEFORE UPDATE ON user_room_scans
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Backfill from legacy project_room_scans (owner as library user).
INSERT INTO user_room_scans (
    id, user_id, scan_type, parent_scan_id, room_label, section,
    structure_label, captured_at, derived, created_at, updated_at
)
SELECT
    prs.id,
    p.owner_user_id,
    prs.scan_type,
    prs.parent_scan_id,
    prs.room_label,
    prs.section,
    CASE WHEN prs.scan_type = 'structure' THEN prs.room_label ELSE NULL END,
    prs.captured_at,
    prs.derived,
    prs.created_at,
    prs.updated_at
FROM project_room_scans prs
JOIN projects p ON p.id = prs.project_id
ON CONFLICT (id) DO NOTHING;

INSERT INTO project_room_scan_links (project_id, scan_id, is_active, linked_at)
SELECT prs.project_id, prs.id, prs.is_active, prs.created_at
FROM project_room_scans prs
ON CONFLICT (project_id, scan_id) DO NOTHING;
