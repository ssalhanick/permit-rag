-- db/migrations/043_bids_core.sql
-- Contractor marketplace milestone 3: structured bids, aligned with the
-- BidDocument shape the (unbuilt) Bid Evaluator (docs/agent_architecture.md,
-- agent #16) was already designed around.
-- ─────────────────────────────────────────────────────────
-- Marketplace bids are native, structured submissions rather than uploaded
-- PDFs -- so every field the Bid Evaluator's BidDocument schema expects
-- (contractor identity, license #, line items split labor/material,
-- allowances, exclusions, payment schedule, timeline, warranty, change-order
-- terms, lien-waiver language, insurance certs) is captured directly here,
-- and bids/evaluator.py can score any bid the same way regardless of whether
-- it arrived through this table or a future PDF-upload path.
--
-- license_id does double duty for BidDocument's "license #" AND "insurance
-- cert reference" -- contractor_licenses (migration 044) already carries
-- both, so one FK covers both fields rather than duplicating insurance data
-- onto every bid.
--
-- The completeness checklist and red-flag rule table are Python modules
-- (bids/required_clauses.py, bids/red_flags.py), not tables here -- same
-- "git-tracked logic vs. runtime data" split forms/ontology.py already
-- established. labor_rate_benchmarks below IS a table because it's numeric
-- reference data, not logic.

CREATE TABLE bids (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id                  uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    contractor_profile_id       uuid NOT NULL REFERENCES contractor_profiles(id) ON DELETE CASCADE,
    license_id                  uuid NOT NULL REFERENCES contractor_licenses(id),
    status                      text NOT NULL DEFAULT 'submitted'
                                     CONSTRAINT chk_bids_status
                                     CHECK (status IN ('submitted', 'withdrawn', 'declined', 'awarded')),
    total_price                 numeric(12,2) NOT NULL,
    labor_total                 numeric(12,2),
    material_total               numeric(12,2),
    allowances                  jsonb NOT NULL DEFAULT '[]',        -- [{description, amount}]
    exclusions                  jsonb NOT NULL DEFAULT '[]',        -- [{description}]
    payment_schedule             jsonb NOT NULL DEFAULT '[]',        -- [{milestone, percent|amount, trigger}]
    permit_responsibility       text
                                     CONSTRAINT chk_bids_permit_responsibility
                                     CHECK (permit_responsibility IS NULL OR permit_responsibility IN ('contractor', 'homeowner')),
    timeline_start               date,
    timeline_end                 date,
    timeline_notes                text,
    warranty_text                 text,
    warranty_years                numeric(4,1),
    change_order_terms           text,
    lien_waiver_included          boolean NOT NULL DEFAULT false,
    materials_source             text NOT NULL DEFAULT 'unspecified'
                                     CONSTRAINT chk_bids_materials_source
                                     CHECK (materials_source IN (
                                         'unspecified', 'homeowner_supplied',
                                         'contractor_supplied_manual', 'contractor_supplied_connector'
                                     )),
    materials_source_connector   text,   -- e.g. 'home_depot_pro' | 'lowes_pro' -- tag only, no live integration yet
    materials_source_notes       text,   -- the generic manual-entry fallback's free text
    llm_red_flags                 jsonb,  -- populated once by the LLM-assisted evaluator pass; NULL = not yet evaluated
    llm_evaluated_at              timestamptz,
    notes                         text,
    submitted_at                  timestamptz,
    decided_at                    timestamptz,   -- award/decline timestamp
    created_at                    timestamptz NOT NULL DEFAULT now(),
    updated_at                    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_bids_project     ON bids (project_id);
CREATE INDEX idx_bids_contractor  ON bids (contractor_profile_id);
CREATE INDEX idx_bids_status      ON bids (status);

-- One active (submitted) bid per contractor per project. Revising a bid is
-- withdraw-then-resubmit, not an in-place edit.
CREATE UNIQUE INDEX uq_bids_one_active_per_contractor_project
    ON bids (project_id, contractor_profile_id)
    WHERE status = 'submitted';

CREATE TRIGGER trg_bids_updated_at
    BEFORE UPDATE ON bids
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TABLE bid_line_items (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bid_id                uuid NOT NULL REFERENCES bids(id) ON DELETE CASCADE,
    line_index            integer NOT NULL,
    description           text NOT NULL,
    quantity              numeric NOT NULL,
    unit                  text NOT NULL,   -- same vocabulary as commerce/takeoff.py: sq_ft | linear_ft | each
    unit_price            numeric(12,2) NOT NULL,
    labor_amount          numeric(12,2) NOT NULL DEFAULT 0,
    material_amount       numeric(12,2) NOT NULL DEFAULT 0,
    labor_hours           numeric(8,2),                -- optional; enables labor_rate_benchmarks comparison when present
    canonical_work_item   text,                         -- forward-compat seam for a future per-line ontology mapping
    created_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_bid_line_items_bid_index UNIQUE (bid_id, line_index)
);

CREATE INDEX idx_bid_line_items_bid ON bid_line_items (bid_id);

-- Seeded reference data (scripts/seed_labor_rate_benchmarks.py), not logic --
-- a real table, unlike required_clauses.py/red_flags.py above.
CREATE TABLE labor_rate_benchmarks (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    trade             text NOT NULL,
    region            text NOT NULL DEFAULT 'DFW',
    low_hourly_rate   numeric(8,2) NOT NULL,
    high_hourly_rate  numeric(8,2) NOT NULL,
    source            text NOT NULL,   -- citation, so "estimate, not authoritative" is traceable per row
    effective_date    date,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_labor_rate_benchmarks_trade_region UNIQUE (trade, region)
);

CREATE INDEX idx_labor_rate_benchmarks_trade ON labor_rate_benchmarks (trade);

CREATE TRIGGER trg_labor_rate_benchmarks_updated_at
    BEFORE UPDATE ON labor_rate_benchmarks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Now that bids exists, attach the FK migration 042 deferred.
ALTER TABLE projects
    ADD CONSTRAINT fk_projects_awarded_bid FOREIGN KEY (awarded_bid_id) REFERENCES bids(id);

COMMENT ON TABLE bids IS
    'A contractor''s structured bid on an open project, shaped to match the '
    'BidDocument schema the (unbuilt) Bid Evaluator agent was designed around '
    '(docs/agent_architecture.md) -- so bids/evaluator.py''s completeness, '
    'price-reasonableness, and red-flag analysis runs on every marketplace '
    'bid without a separate PDF-parsing step.';
COMMENT ON COLUMN bids.license_id IS
    'The contractor_licenses row backing this bid -- covers both BidDocument''s '
    '"license #" and "insurance cert reference" in one FK.';
COMMENT ON COLUMN bids.llm_red_flags IS
    'Novel red flags an LLM pass found beyond the deterministic rule table '
    '(bids/red_flags.py), computed once at submission via rag/agent_runtime.py '
    'and cached here -- never recomputed on read.';
COMMENT ON TABLE labor_rate_benchmarks IS
    'Seeded public DFW hourly-rate ranges per trade (scripts/seed_labor_rate_benchmarks.py). '
    'No free authoritative source exists (RSMeans is paid) -- every price-reasonableness '
    'output derived from this table must be labeled an estimate with its source.';
