-- db/migrations/026_design_intent_usage_project_fk.sql
-- design_intent_usage.project_id had no ON DELETE rule, unlike every other
-- project_id FK in the schema. This blocked hard_delete_project with a
-- ForeignKeyViolation whenever a project had design-intent usage logged
-- against it. Detach on delete (SET NULL) to match query_log, since this
-- table is a token-usage/billing ledger that should survive project deletion.

ALTER TABLE design_intent_usage
    DROP CONSTRAINT design_intent_usage_project_id_fkey;

ALTER TABLE design_intent_usage
    ADD CONSTRAINT design_intent_usage_project_id_fkey
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
