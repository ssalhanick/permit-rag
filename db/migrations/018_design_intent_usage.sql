-- db/migrations/018_design_intent_usage.sql
-- Token usage accounting for cloud design-intent LLM calls.

CREATE TABLE design_intent_usage (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid NOT NULL REFERENCES users(id),
    project_id    uuid REFERENCES projects(id),
    room_scan_id  uuid NOT NULL,
    input_tokens  int NOT NULL DEFAULT 0,
    output_tokens int NOT NULL DEFAULT 0,
    model         text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_design_intent_usage_user_month
    ON design_intent_usage (user_id, created_at DESC);

COMMENT ON TABLE design_intent_usage IS
    'Per-call token accounting for design-intent LLM previews (cloud only).';
