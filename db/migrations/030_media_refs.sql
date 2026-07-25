-- db/migrations/030_media_refs.sql
-- Phase 4 second pass -- Media Curator (agent #17).
-- ─────────────────────────────────────────────────────────
-- A curated table of vetted how-to video links for the DIY answer path.
--
-- The Media Curator NEVER emits a URL from model memory (dead links). It has
-- two sourced paths: this table, and (a later slice) a web_search restricted to
-- allowed_domains:["youtube.com"]. The Guardrail rejects any URL from neither.
-- This migration ships the deterministic path -- a lookup, no LLM, $0 -- which
-- satisfies the "zero unsourced URLs" hard gate by construction: every row here
-- is a hand-vetted link.
--
-- Uses text + CHECK rather than enums (matching 026_agent_traces) so a new
-- provider never requires an ALTER TYPE. Additive and idempotent.
--
-- Numbering: 030 was tentatively pencilled for Phase 6 (ontology + bids) in
-- docs/agent_architecture.md, but that phase is unshipped (nothing exists at
-- 030). Media Curator takes 030; the planned ontology/bids migration cascades
-- to 031. Same additive-cascade convention used for 028/029.

CREATE TABLE IF NOT EXISTS media_refs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_key          text NOT NULL,                    -- normalized task, e.g. 'install_gfci_outlet'
    title             text NOT NULL,
    url               text NOT NULL,
    provider          text NOT NULL DEFAULT 'youtube',  -- host allow-list anchor
    jurisdiction      text,                             -- null = national how-to (applies everywhere)
    relevance_note    text,
    last_verified_at  timestamptz,                      -- link-liveness signal (Freshness Watcher, later)
    active            boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT media_refs_provider_chk CHECK (provider IN ('youtube')),
    CONSTRAINT media_refs_url_https_chk CHECK (url LIKE 'https://%'),
    CONSTRAINT media_refs_task_url_uniq UNIQUE (task_key, url)  -- idempotent seeding
);

-- The curator's hot path: active rows for a task_key, jurisdiction-aware.
CREATE INDEX IF NOT EXISTS idx_media_refs_task
    ON media_refs (task_key)
    WHERE active;

COMMENT ON TABLE media_refs IS
    'Curated, vetted how-to video links for the DIY answer path (Media Curator, '
    'agent #17). The deterministic sourced path -- every row is hand-verified, so '
    'the "zero unsourced URLs" gate holds by construction.';
COMMENT ON COLUMN media_refs.task_key IS
    'Normalized task the video teaches, e.g. install_gfci_outlet. The curator '
    'derives a task_key from the query + permit types and looks it up here.';
COMMENT ON COLUMN media_refs.jurisdiction IS
    'Municipality this link is specific to (matches documents.municipality), or '
    'NULL for a national how-to. Jurisdiction matches are preferred over national.';
COMMENT ON COLUMN media_refs.last_verified_at IS
    'When the link was last confirmed live. NULL = never verified. A future '
    'Freshness-Watcher slice re-checks liveness and updates this.';
