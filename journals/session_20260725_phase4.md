# Session 2026-07-25 — Agent architecture Phase 4 core (Prompt Router + fragment library)

Branch: `agents/phase-4`. Machine A (repo machine, empty DB, no corpus).

## Task (restated at session start)

Phase 3 is DONE and on prod (STATE + journal agree; the "operational tail" in the
old next-session prompt was already completed 2026-07-24 — journal wins). So the
real task is **Phase 4 core — Prompt Router + versioned fragment library +
persona-aware `max_tokens` + Guardrail truncation trip + kickoff demotion**, own
branch, migration **029**. Media Curator (#17) deferred to a second pass (owner
chose "core first"). Eval hooks added to the plan at the owner's request
(fragment-versioned traces, per-persona experiments, deterministic
appropriateness checks). Machine A limits: `pytest` (mocked), `ruff`,
`verify_phase2 --no-db`; DB/corpus/RAGAs on machine B.

## What was accomplished (all machine A, mocked/offline)

### Migration 029 — `db/migrations/029_prompt_fragments.sql`
- `ADD COLUMN IF NOT EXISTS` for `projects.experience` and
  `projects.project_notes`. Additive, idempotent, no data migration.
  `custom_system_prompt` retained for back-compat read; no longer written.

### `rag/prompts/` — the versioned fragment library
- `__init__.py`: loader that parses a `<!-- version: N -->` header per file,
  exposes `Fragment(dimension, key, version, body)` with
  `id = "dimension:key@version"`, `get_fragment`, `base_fragment`, `keys_for`,
  `library_version()` (sha256 digest over all fragment ids), and `bound_notes()`
  (control-char strip + collapse + word-boundary truncate to ≈200 tokens).
- Fragments as `.md` files (git-tracked, source of truth): `base` +
  persona `{diy, contractor, hiring_contractor, research}` + 7 jurisdictions
  (`dallas, plano, frisco, mckinney, fort_worth, tx, federal`) + 5 intents
  (`compliance_lookup, how_to, bid_review, cost_estimate, form_fill`) + 2
  experience (`first_timer, experienced`). `base` carries the non-negotiable
  grounding/citation rules (mirrors today's `SYSTEM_PROMPT` core → default path
  shouldn't regress faithfulness).

### `rag/agents/prompt_router.py` — agent #2
- `route(persona, jurisdiction, intent, experience, project_notes) -> RoutedPrompt`.
  Composition `base ∥ persona ∥ jurisdiction ∥ intent ∥ experience ∥ notes` by
  **lookup, no LLM call**.
- **`research` default, never `diy`** (`_resolve_persona`); sets
  `persona_defaulted` for the Clarification nudge.
- `max_tokens_for(persona, intent)` — contractor 640 / research 896 /
  hiring_contractor 1792 / diy 2048, verbose-intent bonus, ceiling 4096, floor
  512. This is the kill for the hard-coded 1024.
- Jurisdiction alias map (`Fort Worth → fort_worth`, `Texas → tx`, `federal`).
- Missing requested fragment → recorded in `.missing` + logged (Crystallizer
  signal), never fatal. Registered in `rag/agents/__init__.py` (roster now 12).

### `rag/agents/guardrail.py` — agent #4 slice
- `check_truncation(gen, query, entity_id, run_id)`: on
  `stop_reason == 'max_tokens'`, files a deduped `answer_truncated` action item
  via `db.client.upsert_action_item` (source_agent `guardrail`, non-blocking).
  Never raises. `rag/agents/ → db/` is allowed, so it writes directly.

### Wiring — generator + manager
- `rag/generator.py`: `generate_answer` gains `routed: RoutedPrompt | None` and
  `max_tokens: int | None`. `_resolve_prompt` picks routed system + persona
  `max_tokens` + fragment ids when routed, else the legacy path with the 1024
  fallback. `prompt_fragment_ids` + a composite `prompt_version`
  (`library_version`) now land on the answer step. `_generate_with_ollama` takes
  a precomputed `system`. **Un-routed default unchanged** →
  `test_generator_runtime_fold` (incl. `test_max_tokens_is_still_1024`) stays
  green by construction.
- `rag/agents/manager.py` `_generate`: `_route_prompt` (deterministic
  `record_step("prompt_router", …)` carrying fragment ids), `_derive_intent`
  (cheap keyword heuristic; unknown → compliance_lookup), passes `routed=` to the
  generator, then `_guard_truncation`. Router failure degrades to the legacy
  prompt. `persona_defaulted` threads via `_PlanState`/`ManagerResult` to
  `AnswerResponse.persona_nudge`.

### Kickoff demotion + schema
- `KICKOFF_SYSTEM_PROMPT` asks for bounded `notes` (facts, <200 tokens), not a
  `custom_system_prompt` blob; both kickoff returns run through
  `_bound_kickoff_notes`. `KickoffChatResponse.notes` added; `custom_system_prompt`
  marked deprecated. `UpdateProjectRequest`/`ProjectResponse` + `projects.py`
  writer + `db.client.update_project` + `rag/project_context.py` learn
  `experience`/`project_notes`. `AnswerResponse.persona_nudge` added.

### Eval hooks
- `evaluation/langsmith_eval.run_pipeline` takes `persona`/`experience`/`intent`,
  routes through the fragment library, passes `routed=` to the generator, and
  emits `persona` + `prompt_fragment_ids` + `prompt_library_version` + `stop_reason`
  in the output for comparable per-persona experiments. `target()` reads
  `persona`/`experience`/`intent` from dataset inputs.
- `evaluation/persona_checks.py` — deterministic persona-appropriateness
  (`hiring_contractor` → questions + red-flags; `diy` → steps + safety; contractor
  /research → citation present). Blunt string/regex; the LLM judge is Phase 5.

### Tests (machine A)
- `test_prompt_router.py` (research-default-never-diy, composition order,
  fort-worth alias, missing-fragment, max_tokens table, notes bounding, library
  coverage/versioning), `test_guardrail.py` (files item / no-op / never-raises /
  entity_id), `test_persona_checks.py`, `test_generator_routing.py` (routed
  system + max_tokens + fragment ids reach the runtime; explicit override;
  un-routed default 1024).

## Verification performed (machine A)

- `python -m py_compile` over **all** changed files → clean.
- Fragment-loader smoke (`from rag import prompts`, stdlib-only, no DB): all
  keys resolve, `base:base@1`, `library_version()` = `lib-13e9450e79e2`,
  `bound_notes` truncates correctly.
- **NOT run here (owner runs python modules manually):** `pytest`, `ruff`,
  `verify_phase2 --no-db`. Nothing DB/corpus/RAGAs (machine B).

## Findings / decisions worth keeping

1. **The un-routed path is the RAGAs safety net.** `generate_answer` with no
   `routed` keeps the legacy system prompt + 1024, so the eval harnesses and the
   Phase-2 fold test are behaviour-identical. The persona change is opt-in via the
   Manager passing a `routed` prompt.
2. **`research` fragment mirrors today's grounding rules** deliberately, so the
   default/anonymous answer path shouldn't move faithfulness. Persona fragments
   layer voice/depth on top of a frozen `base`.
3. **`LLM_MODEL` override kept.** Model choice is unchanged this pass — handing it
   to the Budget Governor is deferred (the plan's "Phase 4 drops the override"
   was not done here; STATE decisions log corrected).
4. **Caching still below floor.** A single composed persona prompt is under the
   4096-token Haiku/Opus cache minimum, so `cache_read` stays 0 — not
   over-claimed. Plumbing is correct for when the prefix grows.
5. **Guardrail writes directly to db.** `rag/agents/ → db/` is in-bounds, so the
   truncation trip files its own action item (no api round-trip).

## Machine B block — Phase 4 verification (run in order)

```powershell
.\.venv\Scripts\Activate.ps1
# Machine A first (this repo can run these — mocked/offline):
py -m pytest tests/ -q                 # prior 442 + Phase-4 tests
py -m ruff check rag/ tests/ evaluation/
py scripts/verify_phase2.py --no-db    # 18/18, incl. the anthropic grep
# Machine B (corpus):
py scripts/check_migration_details.py --local                    # read-only, first
py scripts/apply_migration.py db/migrations/029_prompt_fragments.sql
# 3-persona demo: same question routed as diy / contractor / hiring_contractor.
# Fresh LIVE RAGAs baseline (cache off) BEFORE RAGAs gates anything:
py -m evaluation.ragas_eval --export --no-answer-cache
```

## Commit messages (this session)

```
feat: Phase 4 core — Prompt Router + versioned fragment library + persona-aware max_tokens + Guardrail truncation trip
```

(Single logical change; if splitting is preferred:)

```
feat: rag/prompts versioned fragment library + migration 029 (projects.experience/project_notes)
feat: prompt_router (agent #2) — lookup composition, research default, persona/intent max_tokens
feat: guardrail truncation trip files an action item on stop_reason==max_tokens
feat: wire router through generator+manager; kickoff demoted to bounded notes; persona_nudge
feat: Phase 4 eval hooks — fragment-versioned traces, per-persona langsmith_eval, persona_checks
```

## Prompt for next session

> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md, and
> docs/agent_architecture.md before touching anything. Restate the current task
> first — AGENTS.md pre-session protocol.
>
> **Phase 4 core is BUILT on `agents/phase-4` but NOT yet verified or deployed.**
> First, verify: machine A `py -m pytest tests/ -q` (prior 442 + the four new
> Phase-4 test files), `py -m ruff check rag/ tests/ evaluation/`,
> `py scripts/verify_phase2.py --no-db` (18/18). Fix anything red. Then machine B:
> apply `029_prompt_fragments.sql`, run the 3-persona demo (same question as
> `diy`/`contractor`/`hiring_contractor` → three genuinely different answers —
> the headline demo), and establish a fresh **live** RAGAs baseline
> (`--no-answer-cache`) — measure, don't gate. Then merge to `deployment/sites`
> and GHA-deploy (apply 029 on prod RDS at deploy).
>
> **Then Phase 4 second pass — Media Curator (#17):** sourced URLs only
> (`web_search` + `allowed_domains:["youtube.com"]`, or a curated `media_refs`
> table); Guardrail rejects any URL from neither; wire into the `diy` path
> (Media Curator ∥ Answer Generator). Own branch.
>
> Carried, still open: `checksum_sha256` backfill (source-identity, separate);
> the live multi-sample RAGAs baseline is the start of clearing eval-harness debt
> (STATE punch 3); q6/Dallas is a retrieval (3-part PDF) problem, not governance.
```
