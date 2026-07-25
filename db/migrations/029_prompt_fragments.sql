-- 029_prompt_fragments.sql  (Phase 4 — Prompt Router)
-- =====================================================
-- Demotes the single free-text LLM blob (projects.custom_system_prompt,
-- migration 020) to bounded, sanitized notes, and adds the experience
-- modifier the Prompt Router composes into the system prompt.
--
-- The fragment library itself is NOT in the database. Fragments are
-- hand-authored, versioned files under rag/prompts/ (git-tracked, the source
-- of truth). This migration only touches the projects row: the per-request
-- fragment SELECTION (persona || jurisdiction || intent || experience) is a
-- lookup, and only two of those inputs are stored on the project.
--
-- Additive and idempotent. custom_system_prompt is LEFT IN PLACE so existing
-- rows keep reading — the kickoff chat simply stops writing a full prompt into
-- it and writes project_notes instead. A later migration may drop it once no
-- row depends on it.

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS experience    TEXT,
    ADD COLUMN IF NOT EXISTS project_notes TEXT;

COMMENT ON COLUMN projects.experience    IS
    'Prompt Router experience modifier: first_timer | experienced. NULL = unset.';
COMMENT ON COLUMN projects.project_notes IS
    'Bounded, sanitized project notes (<=200 tokens) composed LAST into the '
    'system prompt by the Prompt Router. Replaces the old unversioned '
    'custom_system_prompt blob (migration 020), which is retained for back-compat '
    'read only and no longer written by the kickoff chat.';
