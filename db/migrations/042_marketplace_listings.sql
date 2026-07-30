-- db/migrations/042_marketplace_listings.sql
-- Contractor marketplace milestone 2: open a project up for bidding.
-- ─────────────────────────────────────────────────────────
-- Extends `projects` directly, matching every prior project-concept addition
-- (014 address/work_types, 019 GIS, 020 budget/persona, 021 materials, 023
-- lifecycle, 029 experience/project_notes) rather than introducing a satellite
-- table for a 1:1 concept.
--
-- text + CHECK rather than a native ENUM TYPE, matching this repo's own
-- precedent for young, evolving status fields (users.role / chk_user_role,
-- altered in-place in migration 024) instead of the harder-to-evolve native
-- enums (document_status, authority_level) used for stable domains.
--
-- Numbers 035 (query_log.session_id) and 036 (design_intent_usage.kind) are
-- already applied in prod. 034 separately fills the Phase-6 slot reserved in
-- STATE.md for contractor_profiles. 037-041 are deliberately skipped, not
-- reused -- two other concurrent plans already claimed them by name:
-- docs/jurisdiction_and_gis_runbook.md Phase 1 names
-- 037_match_chunks_jurisdiction_hierarchy.sql (required) and
-- 038_jurisdiction_fk_constraints.sql (optional); the document-upload plan
-- names 039_overlays.sql, 040_document_visibility.sql, and
-- 041_user_trust.sql. This feature picks up at 042 so both of those can land
-- exactly as documented, no renumbering needed on their side. See STATE.md's
-- "Migration numbering" note for the full reservation ledger.
--
-- awarded_bid_id has no FK yet -- the `bids` table it references doesn't
-- exist until migration 043. The FK is attached there once both tables exist.

ALTER TABLE projects
    ADD COLUMN marketplace_status text NOT NULL DEFAULT 'unlisted'
        CONSTRAINT chk_projects_marketplace_status
        CHECK (marketplace_status IN ('unlisted', 'open', 'awarded', 'closed')),
    ADD COLUMN listed_at         timestamptz,
    ADD COLUMN bidding_closes_at timestamptz,
    ADD COLUMN awarded_bid_id    uuid;

CREATE INDEX idx_projects_marketplace_open
    ON projects (marketplace_status)
    WHERE marketplace_status = 'open';

-- Serves the marketplace browse/filter query (by trade); didn't exist before
-- because no prior feature filtered projects by work_types at scale.
CREATE INDEX idx_projects_work_types_gin
    ON projects USING gin (work_types);

COMMENT ON COLUMN projects.marketplace_status IS
    'unlisted (default, not on the marketplace) -> open (homeowner accepting '
    'bids) -> awarded (one bid accepted, others auto-declined) -> closed '
    '(bidding ended without an award). Independent of permit status -- any '
    'project can be listed, not just ones with a pulled permit.';
COMMENT ON COLUMN projects.awarded_bid_id IS
    'The winning bids.id once marketplace_status = awarded. FK added in '
    'migration 043 after the bids table exists.';
