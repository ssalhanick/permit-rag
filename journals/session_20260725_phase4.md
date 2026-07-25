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

Follow-ups this session (verification + demo):

```
style: ruff autofix on Phase 4 test files (import order, bool over ternary)   # 5fbdcb4 (also swept in scripts/persona_demo.py)
chore: persona_demo default query matches the corpus (was abstaining)
fix(frontend): drop deprecated jsconfig baseUrl; paths resolve relative to config
```

(Single logical change; if splitting is preferred:)

```
feat: rag/prompts versioned fragment library + migration 029 (projects.experience/project_notes)
feat: prompt_router (agent #2) — lookup composition, research default, persona/intent max_tokens
feat: guardrail truncation trip files an action item on stop_reason==max_tokens
feat: wire router through generator+manager; kickoff demoted to bounded notes; persona_nudge
feat: Phase 4 eval hooks — fragment-versioned traces, per-persona langsmith_eval, persona_checks
```

## Verification — machine A + machine B (2026-07-25)

**Machine A — PASSED.** `py -m pytest tests/ -q` → **474 passed** (was 442; +32).
`ruff` clean on all Phase-4 files; the ~15 remaining `ruff check rag/ tests/` hits
are pre-existing (`test_sprint9` SIM117/SIM210 + the `SYSTEM_PROMPT` en-dash
RUF001) — none introduced here. **Do not "fix" the en-dash**: it is live prompt
text and changing it would perturb the RAGAs baseline. `verify_phase2 --no-db` →
18/18; roster now lists `prompt_router` + `guardrail`.

*Ruff housekeeping note:* the owner's `ruff --fix rag/ tests/ evaluation/` applied
88 safe autofixes, 24 of them to unrelated pre-existing files. Those 24 were
`git restore`d; only the 2 cosmetic fixes to the new Phase-4 test files were kept
(committed in `5fbdcb4`).

**Machine B — PASSED.** Migration 029 applied. Added `scripts/persona_demo.py`
(target-safe via `_db_target`; read-only; runs one question across personas and
prints the routing evidence). First run abstained on a vague default query
("remodel my kitchen") — retrieval below the grounding floor, which happens
*before* routing, so it shows nothing; fixed by defaulting to a corpus-matching
query (the abstain is expected behaviour, not a bug). On "bathroom addition
permits in Dallas":

| Persona | max_tokens | output | stop_reason | appropriateness |
|---------|-----------|--------|-------------|-----------------|
| diy | 2048 | 407 | end_turn | 100% |
| contractor | 640 | 301 | end_turn | 100% |
| hiring_contractor | 1792 | 839 | end_turn | 100% |

Three genuinely different answers, correct fragment composition
(`base ∥ persona ∥ jurisdiction:dallas ∥ intent:compliance_lookup`), **zero
truncation**, and `hiring_contractor` emitted its "Questions to ask" + "Red flags"
sections. **All Phase 4 acceptance items met.** (The answers correctly abstain on
the *specifics* — retrieval pulled tangential Dallas ordinance chunks, the known
3-part-PDF weakness — which is the grounding rules working faithfully, and a
retrieval concern, not a routing one.)

**Fresh LIVE RAGAs baseline** — `evaluation/results/ragas_20260725_011651.json`,
cache off (every `answer_cache_hit` null). avg_faithfulness **0.843**,
avg_relevancy 0.982, avg_context_precision 0.693, top_sim avg 0.794. Per-query
faithfulness: q0 0.80 · q1 0.75 · q2 0.94 · q3 1.0 · q4 0.92 · q5 1.0 · **q6 0.50**.
The 0.007 miss under 0.85 is entirely q6 ("maximum building height"; its
context_precision is 1.0, so retrieval was right and the answer/judge disagreed —
the documented ±0.15 single-query swing). Critically, **`ragas_eval` measures the
un-routed path** (`generate_answer` with no persona, `ragas_eval.py:657`), so this
confirms Phase 4 did not move default-path faithfulness — the non-regression goal.
Measure-not-gate this phase; the first clean *live* baseline (one sample; a real
gate needs 3+ to average out q6). Not a deploy blocker.

## Prompt for next session

> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md, and
> docs/agent_architecture.md before touching anything. Restate the current task
> first — AGENTS.md pre-session protocol.
>
> **Phase 4 core is BUILT + VERIFIED on `agents/phase-4` (machine A 474 pytest +
> machine B 3-persona demo + live RAGAs baseline), NOT yet deployed.** First,
> deploy: merge `agents/phase-4` → `deployment/sites`, GHA-deploy, and **apply
> `029_prompt_fragments.sql` on prod RDS** at deploy (additive; safe). Prod smoke:
> a persona-set project's `/query/answer` returns a routed answer, and an
> anonymous/no-persona query returns `persona_nudge` (the Clarification nudge). See
> the acceptance gate + baseline read in this journal / STATE before re-running
> anything — don't redo the verification.
>
> **Then Phase 4 second pass — Media Curator (#17):** sourced URLs only
> (`web_search` + `allowed_domains:["youtube.com"]`, or a curated `media_refs`
> table); Guardrail rejects any URL from neither; wire into the `diy` path
> (Media Curator ∥ Answer Generator). Own branch.
>
> Carried, still open: a **multi-sample** live RAGAs baseline (the 2026-07-25 run
> is one sample, avg 0.843, q6=0.50 drags it under 0.85) + repoint `eval_guard`
> off the stale cached `ragas_20260531` baseline (STATE punch 3); `checksum_sha256`
> backfill (source-identity, separate); the `NLI inference failed ('type')`
> classifier warning (non-fatal keyword fallback); q6/Dallas is a retrieval (3-part
> PDF) problem, not governance — all pre-existing, none Phase 4.
```
