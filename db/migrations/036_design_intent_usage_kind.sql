-- db/migrations/036_design_intent_usage_kind.sql
-- Account for generative room-preview images alongside design-intent LLM calls.
-- ─────────────────────────────────────────────────────────
-- `POST /commerce/room-preview-image` calls a paid image API (gpt-image-1 or
-- Leonardo) and until now recorded nothing: the route took `_current_user` and
-- discarded it, so there was no per-user spend cap and no way to audit who
-- generated what. Design-intent already had both (`_check_token_cap` +
-- `insert_design_intent_usage`), so image generations reuse this table rather
-- than getting one of their own.
--
-- Two changes make that possible:
--   * `kind` separates the two call types. Counting images by matching the
--     `model` string would be fragile — the image provider can be openai,
--     leonardo, or mock, and the ladder can change design-intent models freely.
--   * `room_scan_id` becomes nullable. The image request carries an utterance
--     and overlays but no scan id, and inventing one to satisfy NOT NULL would
--     put fake ids in the audit trail.
--
-- `kind` defaults to 'design_intent', which is the correct label for every
-- existing row, so no backfill is needed.

ALTER TABLE design_intent_usage
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'design_intent';

ALTER TABLE design_intent_usage
    ALTER COLUMN room_scan_id DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_design_intent_usage_user_kind_month
    ON design_intent_usage (user_id, kind, created_at DESC);

COMMENT ON COLUMN design_intent_usage.kind IS
    'Which metered call produced this row: design_intent (LLM overlay parse) or '
    'room_image (generative preview image). Drives the per-kind monthly caps.';

COMMENT ON COLUMN design_intent_usage.room_scan_id IS
    'Room scan the call was made against. NULL for room_image rows, which are '
    'requested from the design page without a scan id in the payload.';
