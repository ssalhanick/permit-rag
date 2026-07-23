-- db/migrations/027_agent_action_item_dedupe.sql
-- Corrects 026_agent_traces.sql, which shipped agent_action_items.entity_type
-- and .entity_id as nullable.
--
-- NULLs never conflict in a unique index, so uq_agent_action_items_open_entity
-- silently did not dedupe entity-less items -- exactly what a scheduled anomaly
-- sweep files. Two upserts produced two rows; a nightly sweep would accumulate
-- one duplicate per run forever.
--
-- Delivered as a separate migration rather than an edit to 026 because 026 has
-- already been applied to local and production, and AGENTS.md forbids modifying
-- a migration after deployment.
--
-- The index itself needs no change: it is already defined over the bare
-- columns, and becomes correct the moment they stop being nullable.
--
-- Idempotent and safe to re-run. Additive only; no data is destroyed.
--
-- NOTE ON NUMBERING: there are two migrations numbered 026 in this directory
-- (026_agent_traces.sql and 026_design_intent_usage_project_fk.sql). The
-- collision is recorded rather than corrected, because renaming a file that has
-- already been applied by name on multiple databases is riskier than the
-- duplicate. scripts/check_migrations.py probes both independently.

-- Existing rows first, so SET NOT NULL cannot fail on legacy data.
UPDATE agent_action_items SET entity_type = '' WHERE entity_type IS NULL;
UPDATE agent_action_items SET entity_id   = '' WHERE entity_id   IS NULL;

ALTER TABLE agent_action_items
    ALTER COLUMN entity_type SET DEFAULT '',
    ALTER COLUMN entity_id   SET DEFAULT '';

ALTER TABLE agent_action_items
    ALTER COLUMN entity_type SET NOT NULL,
    ALTER COLUMN entity_id   SET NOT NULL;

COMMENT ON COLUMN agent_action_items.entity_type IS
    'Entity kind the item concerns, or '''' for a global item. NOT NULL so the '
    'open-item dedupe index applies -- NULLs would never conflict.';
COMMENT ON COLUMN agent_action_items.entity_id IS
    'Entity identifier, or '''' for a global item. NOT NULL for the same reason.';
