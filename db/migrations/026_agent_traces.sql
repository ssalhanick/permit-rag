-- db/migrations/026_agent_traces.sql
-- Phase 0 of the agent architecture: the trace store.
--
-- Everything in the meta tier (Evaluator, Performance Review, Optimizer,
-- Crystallizer) and the superadmin dashboard reads from these tables. They
-- exist before any agent so that history accumulates from day one -- a
-- Crystallizer with no traces has nothing to crystallize.
--
-- Uses text + CHECK rather than enums (matching 025_project_delete_audit_log)
-- so new agent names, kinds, and levels never require an ALTER TYPE.

-- ─────────────────────────────────────────────────────────
-- agent_runs — one row per top-level request
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_runs (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    entrypoint         text NOT NULL,              -- 'query_answer', 'design_intent', ...
    user_id            uuid,                       -- null for anonymous queries
    project_id         uuid,
    intent             text,                       -- 'compliance_lookup', 'bid_review', ...
    persona            text,                       -- mirrors projects.persona at run time
    request_id         text,                       -- correlates with existing API request tracing
    session_id         text,
    model_default      text,
    tokens_in          integer NOT NULL DEFAULT 0,
    tokens_out         integer NOT NULL DEFAULT 0,
    tokens_cache_read  integer NOT NULL DEFAULT 0,
    tokens_cache_write integer NOT NULL DEFAULT 0,
    cost_usd           numeric(12,6) NOT NULL DEFAULT 0,
    latency_ms         integer,
    outcome            text CHECK (outcome IN ('success', 'partial', 'error', 'blocked')),
    error              text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    finished_at        timestamptz
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_entrypoint ON agent_runs (entrypoint, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_runs_project_id ON agent_runs (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_id ON agent_runs (user_id);

-- ─────────────────────────────────────────────────────────
-- agent_steps — one row per agent invocation inside a run
-- ─────────────────────────────────────────────────────────
-- `deterministic` is what makes the Crystallizer measurable: it marks a step
-- served from a rule table instead of a model. `react_iterations` makes loop
-- cost visible, since each iteration re-sends accumulated context.
CREATE TABLE IF NOT EXISTS agent_steps (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             uuid NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    parent_step_id     uuid REFERENCES agent_steps (id) ON DELETE SET NULL,
    agent_name         text NOT NULL,
    step_index         integer NOT NULL DEFAULT 0,
    model              text,                       -- null when deterministic
    deterministic      boolean NOT NULL DEFAULT false,
    react_iterations   integer NOT NULL DEFAULT 0,
    autonomy_level     text CHECK (autonomy_level IN ('L0', 'L1', 'L2', 'L3')),
    prompt_version     text,
    prompt_fragment_ids text[] NOT NULL DEFAULT '{}',
    input_hash         text,                       -- for Crystallizer clustering
    artifact_refs      text[] NOT NULL DEFAULT '{}',
    tokens_in          integer NOT NULL DEFAULT 0,
    tokens_out         integer NOT NULL DEFAULT 0,
    tokens_cache_read  integer NOT NULL DEFAULT 0,
    tokens_cache_write integer NOT NULL DEFAULT 0,
    cost_usd           numeric(12,6) NOT NULL DEFAULT 0,
    latency_ms         integer,
    status             text NOT NULL DEFAULT 'ok'
                           CHECK (status IN ('ok', 'error', 'skipped', 'blocked')),
    error              text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_steps_run_id ON agent_steps (run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_agent_steps_agent_name ON agent_steps (agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_steps_input_hash ON agent_steps (agent_name, input_hash);

-- ─────────────────────────────────────────────────────────
-- agent_corrections — human feedback, attributed to an agent
-- ─────────────────────────────────────────────────────────
-- step_id is nullable: answer-level thumbs-down arrives before the
-- Performance Review agent has attributed it to a specific step.
CREATE TABLE IF NOT EXISTS agent_corrections (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                 uuid REFERENCES agent_runs (id) ON DELETE CASCADE,
    step_id                uuid REFERENCES agent_steps (id) ON DELETE SET NULL,
    source                 text NOT NULL CHECK (source IN ('answer', 'step', 'artifact')),
    attributed_agent       text,
    attribution_confidence numeric(3,2)
                               CHECK (attribution_confidence BETWEEN 0 AND 1),
    severity               text CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    entity_type            text,                   -- artifact-level: 'document', 'bid', 'form_field'
    entity_id              text,
    expected               text,
    actual                 text,
    notes                  text,
    confirmed              boolean NOT NULL DEFAULT false,
    created_by             uuid,
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_corrections_agent
    ON agent_corrections (attributed_agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_corrections_run_id ON agent_corrections (run_id);
CREATE INDEX IF NOT EXISTS idx_agent_corrections_entity
    ON agent_corrections (entity_type, entity_id);

-- ─────────────────────────────────────────────────────────
-- agent_action_items — where "needs a human" goes
-- ─────────────────────────────────────────────────────────
-- A table rather than a dashboard view: a view is a pull mechanism and
-- things rot in it. `blocking` lets a failed document sit in draft status
-- without holding up the rest of the corpus.
CREATE TABLE IF NOT EXISTS agent_action_items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_agent    text NOT NULL,
    kind            text NOT NULL,                 -- 'metadata_incomplete', 'url_changed', ...
    severity        text NOT NULL DEFAULT 'medium'
                        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    blocking        boolean NOT NULL DEFAULT false,
    run_id          uuid REFERENCES agent_runs (id) ON DELETE SET NULL,
    -- NOT NULL DEFAULT '' rather than nullable: NULLs never conflict in a
    -- unique index, so a nullable entity would silently skip the dedupe guard
    -- below for exactly the global checks a scheduled sweep produces. '' means
    -- "no entity". An expression index over COALESCE() would also work, but
    -- Postgres cannot infer a *partial* index from an expression ON CONFLICT.
    entity_type     text NOT NULL DEFAULT '',
    entity_id       text NOT NULL DEFAULT '',
    title           text NOT NULL,
    evidence        jsonb NOT NULL DEFAULT '{}'::jsonb,
    proposed_action text,
    status          text NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'acknowledged', 'resolved', 'dismissed')),
    resolved_by     uuid,
    resolved_at     timestamptz,
    resolution_note text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_action_items_open
    ON agent_action_items (status, severity, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_action_items_entity
    ON agent_action_items (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_agent_action_items_source
    ON agent_action_items (source_agent, status);

-- Dedupe guard: one open item per (source_agent, kind, entity) so a nightly
-- anomaly sweep or a re-run validation does not pile up duplicates. Works for
-- entity-less items too because those columns are NOT NULL DEFAULT '' above.
-- Resolving or dismissing an item drops it out of the predicate, so the same
-- condition can legitimately be raised again later.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_action_items_open_entity
    ON agent_action_items (source_agent, kind, entity_type, entity_id)
    WHERE status IN ('open', 'acknowledged');

-- ─────────────────────────────────────────────────────────
-- agent_autonomy — human-in-the-loop → agent takes the wheel
-- ─────────────────────────────────────────────────────────
-- Enforced in rag/agent_runtime.py, edited from the superadmin dashboard.
-- max_level is a hard ceiling the dashboard cannot raise: some ceilings come
-- straight from AGENTS.md governance rules (never auto-update a changed source
-- URL; never auto-supersede) and some from irreversibility (never auto-submit
-- to a government portal).
--
-- `scope` exists because one agent can have different ceilings per action:
-- the Web Form Navigator may fill at L2 but must submit at L1.
CREATE TABLE IF NOT EXISTS agent_autonomy (
    agent_name     text NOT NULL,
    scope          text NOT NULL DEFAULT 'default',
    current_level  text NOT NULL DEFAULT 'L0'
                       CHECK (current_level IN ('L0', 'L1', 'L2', 'L3')),
    max_level      text NOT NULL DEFAULT 'L1'
                       CHECK (max_level IN ('L0', 'L1', 'L2', 'L3')),
    ceiling_reason text,
    updated_by     uuid,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_name, scope)
);

COMMENT ON COLUMN agent_autonomy.max_level IS
    'Hard ceiling. The dashboard clamps to this; it cannot raise it.';

-- Seed the ceilings that are policy, not preference. Agents absent from this
-- table default to L0 in the runtime -- fail closed, not open.
INSERT INTO agent_autonomy (agent_name, scope, current_level, max_level, ceiling_reason)
VALUES
    ('document_intake',   'url_change',  'L0', 'L0',
     'AGENTS.md: source URL changes are flagged for human review, never auto-updated'),
    ('document_intake',   'supersede',   'L0', 'L1',
     'AGENTS.md: never delete a document -- supersede or repeal only, with human approval'),
    ('metadata_validator', 'enum_fix',   'L0', 'L2',
     'Mechanical and reversible; may be promoted once accuracy is demonstrated'),
    ('metadata_validator', 'semantic',   'L0', 'L1',
     'Changes doc_type/effective_date, which alter retrieval behaviour'),
    ('web_form_navigator', 'fill',       'L0', 'L2',
     'Drafting is reversible'),
    ('web_form_navigator', 'submit',     'L0', 'L1',
     'Irreversible filing with a government body -- always human-approved'),
    ('pdf_form',           'fill',       'L0', 'L2',
     'Produces a draft for human review'),
    ('optimizer',          'default',    'L0', 'L1',
     'Planning decision: propose-only, PR plus human merge'),
    ('crystallizer',       'default',    'L0', 'L1',
     'Planning decision: propose-only, PR plus human merge'),
    ('performance_review', 'high_conf',  'L0', 'L2',
     'High-confidence attributions may be recorded automatically'),
    ('performance_review', 'low_conf',   'L0', 'L0',
     'Never silently record blame the agent is not confident in'),
    ('guardrail',          'default',    'L3', 'L3',
     'A blocker, not a proposer -- per-check human approval would defeat it'),
    ('bid_evaluator',      'default',    'L3', 'L3',
     'Read-only analysis, no side effects'),
    ('freshness_watcher',  'detect',     'L3', 'L3',
     'Detection has no side effects'),
    ('freshness_watcher',  'reingest',   'L0', 'L1',
     'Touches the corpus')
ON CONFLICT (agent_name, scope) DO NOTHING;
