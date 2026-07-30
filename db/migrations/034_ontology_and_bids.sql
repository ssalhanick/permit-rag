-- db/migrations/034_ontology_and_bids.sql
-- Phase 6 — the Field Ontology's per-form mapping corpus.
-- ─────────────────────────────────────────────────────────
-- This is the actual "Phase 6 (ontology/bids)" deliverable STATE.md reserved
-- at 034 (originally planned as 030_ontology_and_bids.sql in
-- docs/agent_architecture.md's Files section, cascaded to 034 once 030-033
-- were claimed by Media Curator/Phase 5 -- see STATE.md's Decisions log).
--
-- Per docs/agent_architecture.md ("What the Field Ontology actually is",
-- Phase 5-6 section): the ontology has 7 parts. Parts 1-3 (canonical field
-- vocabulary, type/validation, source binding) plus part 7 (unit
-- normalization) are the *core* and already shipped in forms/ontology.py --
-- a code module, not a migration, because that vocabulary is git-tracked
-- content that changes with a deploy, not runtime data.
--
-- Part 4 -- "per-form mapping (form fingerprint -> field name/coords ->
-- canonical fact)" -- is "the grind," explicitly called out as the hard
-- part, and *is* runtime data (it accretes one real permit form at a time,
-- across jurisdictions and permit types, via human-reviewed LLM proposals).
-- That's what these two tables are for. Parts 5 (per-bid mapping) and 6
-- (synonym/alias resolution) remain unbuilt -- out of scope here.
--
-- IMPORTANT -- an earlier version of this branch mistakenly built
-- 034_contractor_profiles.sql in this slot, reasoning that a contractor
-- having a SourceBinding.PROFILE-sourced ontology field
-- (contractor.license_number) meant its backing table fulfilled this
-- reservation. It doesn't -- that's a different table for a different
-- feature (the contractor marketplace's own accounts, see
-- 044_contractor_profiles.sql), unrelated to per-form field mapping. Caught
-- and corrected; recorded here and in STATE.md so it isn't repeated.
--
-- Deliberately NOT built here (Phase 7, a separate and much larger piece):
-- forms/pdf_agent.py (AcroForm/OCR field extraction), the LLM mapping-
-- proposal call, and the review-dashboard route. This migration is schema
-- only, for whenever that agent work is scoped.
--
-- Reuse, don't parallel-build: form-family (jurisdiction x permit_type)
-- autonomy graduation (L0/L1/L2) reuses the existing agent_autonomy table
-- (agent_name + scope, e.g. scope='dallas_building_permit') -- no new
-- autonomy columns here. A human correcting a proposed mapping in the
-- review dashboard writes to the existing agent_corrections table -- no new
-- correction/feedback table here either.

CREATE TABLE form_templates (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint       text NOT NULL UNIQUE,   -- hash of (sorted AcroForm field names + page count + normalized title text)
    jurisdiction      text REFERENCES jurisdictions(id),
    permit_type       text NOT NULL,
    version           integer NOT NULL DEFAULT 1,   -- a form revision inserts a new row, never an in-place edit
    field_inventory   jsonb NOT NULL DEFAULT '[]',  -- raw extracted fields (name, label, page rect) -- avoids re-parsing the source form to review
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_form_templates_family_version UNIQUE (jurisdiction, permit_type, version)
);

CREATE INDEX idx_form_templates_family ON form_templates (jurisdiction, permit_type);

CREATE TABLE field_mappings (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    form_template_id  uuid NOT NULL REFERENCES form_templates(id) ON DELETE CASCADE,
    field_name        text NOT NULL,   -- the raw form field identifier (AcroForm name, or OCR-derived label key)
    field_label       text,            -- human-readable label, when available
    canonical_key     text,            -- a forms.ontology.ONTOLOGY key -- validated at the application layer (the
                                        -- vocabulary is a code module, not a table), NULL until proposed/confirmed
    confidence        numeric(4,3),    -- 0.000-1.000, from the LLM proposal call; retained after human review for eval
    rationale         text,            -- the LLM's stated rationale for this mapping
    status            text NOT NULL DEFAULT 'proposed'
                          CONSTRAINT chk_field_mappings_status
                          CHECK (status IN ('proposed', 'confirmed', 'corrected', 'unmappable')),
    reviewed_by       uuid REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_field_mappings_template ON field_mappings (form_template_id);
-- Serves the review dashboard's "sorted by ascending confidence, doubtful ones first" queue.
CREATE INDEX idx_field_mappings_status_confidence ON field_mappings (status, confidence);

CREATE TRIGGER trg_field_mappings_updated_at
    BEFORE UPDATE ON field_mappings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

COMMENT ON TABLE form_templates IS
    'One row per distinct permit-form revision (fingerprint = hash of its '
    'field names + page count + title). Field Ontology part 4 (per-form '
    'mapping), docs/agent_architecture.md. A form revision is a NEW row, '
    'never an in-place edit of an existing one.';
COMMENT ON TABLE field_mappings IS
    'Proposed/confirmed mapping from one form field to a forms.ontology '
    'canonical key. Populated by an LLM proposal call (Phase 7, not built '
    'here), reviewed by a human in a two-pane dashboard (also Phase 7). '
    'Corrections are recorded in the existing agent_corrections table, not '
    'here -- this table only holds current mapping state.';
COMMENT ON COLUMN field_mappings.canonical_key IS
    'A key from forms.ontology.ONTOLOGY (e.g. "work.valuation"). No FK -- '
    'the ontology vocabulary is a git-tracked code module (forms/ontology.py), '
    'not a database table, so this is validated at the application layer.';
