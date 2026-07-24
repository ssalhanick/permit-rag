-- db/migrations/028_metadata_validation.sql
-- Phase 3 of the agent architecture: the Corpus Metadata Validator (agent #13).
--
-- The validator does not need new tables. Its proposals become rows in the
-- existing agent_action_items table (migration 026), and its per-stage results
-- land in the existing ingestion_verifications table. This migration only
-- teaches those two enums the new vocabulary the validator produces:
--
--   verification_stage  += 'metadata'      -- a fifth ingestion stage, run after
--                                             embedding, that checks whether the
--                                             document's metadata is *true*, not
--                                             just present (ingestion/verification.py
--                                             covers bytes/chars/coverage/embeddings).
--   verification_result += 'needs_review'  -- distinct from 'fail': the metadata is
--                                             not provably wrong, but a proposal is
--                                             waiting for human approval in the
--                                             dashboard's metadata review queue.
--
-- NUMBERING: this is 028, not the 027 the plan originally named. 027 is taken by
-- 027_agent_action_item_dedupe.sql, and there is a pre-existing duplicate 026
-- (026_agent_traces.sql + 026_design_intent_usage_project_fk.sql). Both 026s and
-- 027 are already applied by name on local + production, so they are recorded,
-- not renamed (AGENTS.md: never modify a migration after deployment).
--
-- Additive and idempotent. ADD VALUE IF NOT EXISTS is safe to re-run and cannot
-- destroy data. On Postgres 12+ ADD VALUE runs inside a transaction as long as
-- the new label is not *used* in the same transaction -- this migration only
-- declares the labels, so apply_migration.py's single-transaction apply is fine.

ALTER TYPE verification_stage ADD VALUE IF NOT EXISTS 'metadata';

ALTER TYPE verification_result ADD VALUE IF NOT EXISTS 'needs_review';
