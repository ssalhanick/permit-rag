-- db/migrations/033_answer_feedback.sql
-- Phase 5 — Feedback loop: answer-level thumbs up/down (+ optional comment).
-- ─────────────────────────────────────────────────────────
-- The highest-volume / weakest-signal of the three feedback granularities
-- (docs/agent_architecture.md "Feedback capture"): every user can rate an
-- answer. Distinct from `agent_corrections` (an attributed correction with
-- expected/actual) — a thumbs-up is not a correction. A thumbs-DOWN is what the
-- Performance Review agent (#24) later reads together with the run trace to
-- write an attributed `agent_corrections` row; this table is the raw capture.
--
-- Each row references the audit run (`agent_runs.id`) the answer came from, so
-- feedback joins straight onto the trace/cost/latency of the exact generation.
-- One vote per (run_id, user_id): re-voting upserts (a user can flip 👍↔👎 or
-- edit the comment). ON DELETE CASCADE — feedback is meaningless without its run.
--
-- Additive/idempotent (`CREATE TABLE IF NOT EXISTS`), `text + CHECK` (no enums).
--
-- Numbering: Phase 5 feedback takes 033. The earlier note in 032 that "Phase 6
-- ontology/bids cascades to 033" is superseded — Phase 6 now cascades to 034
-- (Phase 5 ships first). See STATE.md migration numbering.

CREATE TABLE IF NOT EXISTS answer_feedback (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      uuid NOT NULL REFERENCES agent_runs (id) ON DELETE CASCADE,
    user_id     uuid,                              -- rater; NULL only if anonymous
    rating      text NOT NULL,
    comment     text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT answer_feedback_rating_chk CHECK (rating IN ('up', 'down')),
    CONSTRAINT answer_feedback_run_user_uniq UNIQUE (run_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_answer_feedback_run
    ON answer_feedback (run_id);
-- Down-votes are the ones Performance Review triages; index them for the queue.
CREATE INDEX IF NOT EXISTS idx_answer_feedback_down
    ON answer_feedback (created_at DESC) WHERE rating = 'down';

COMMENT ON TABLE answer_feedback IS
    'Answer-level thumbs up/down (+ optional comment), one per (run_id, user_id). '
    'Raw high-volume feedback; a down-vote feeds Performance Review (#24), which '
    'attributes it to an agent and writes an agent_corrections row.';
