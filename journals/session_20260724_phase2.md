# Session 2026-07-24 (b) — Agent architecture Phase 2 (Manager + artifacts + budget)

Branch: `agents/phase-2`. Machine A (repo machine, empty DB, no corpus).

## Task (restated at session start)

Port the existing `/query/answer` chain in `api/routes/query.py` behind a
Manager with **zero behaviour change**. Build `rag/agents/manager.py`,
`artifacts.py`, `budget.py`; fold `rag/generator.py`'s inline Anthropic call
into `run_agent`; register everything through `rag/agents/registry.py`; write
`scripts/verify_phase2.py`. Add **no** new answer agents — the phase is
deliberately capability-free so a faithfulness change is attributable to the
abstraction rather than to new agents.

## What was accomplished

### `rag/agents/manager.py` — agent #1
- The whole chain, in order: classify permit types → resolve municipality from
  address → retrieve → grounding guard → conflict detection → upload-conflict
  detection → project context → generate. Ordering is preserved exactly; a
  reorder would be a behaviour change and there is a test asserting the order.
- Expressed as **four ordered waves** against `MAX_ITERATIONS = 6`. Steps inside
  a wave are independent (that is the seam Phase 5's `asyncio.gather` fan-out
  slots into); waves are strictly sequential.
- **Refs only.** Every step's output goes into the artifact store; the loop
  carries `ArtifactRef`s. `ManagerResult` exposes `.retrieval` / `.generation`
  as store lookups, so resolution happens at assembly, outside the loop.
- Failures are signalled with `ManagerError(stage, kind)`, which the route maps
  to status codes. That keeps fastapi out of `rag/agents/` while preserving the
  exact codes *and* the exact message strings (the low-confidence message names
  both thresholds; the empty-corpus message is asserted verbatim by an existing
  test).
- Records one deterministic, zero-cost `manager` trace step carrying
  `react_iterations` and `artifact_refs`.

### `rag/agents/artifacts.py`
- `ArtifactRef(id, kind, summary, token_count, ttl)` + `ArtifactStore`. Expired
  refs raise rather than resolve to stale context.
- `estimate_tokens` is a documented char/4 estimate used **only** for cap
  decisions. Real billing stays with `count_tokens` and the API usage block, in
  the runtime — AGENTS.md forbids a guess in the paid path.

### `rag/agents/budget.py` — agent #3, deterministic
- Per-request cap, ladder selection, degradation (sheds lowest-`reranked_score`
  chunks, floored at 3 so an answer can still carry a citation).
- **Uncapped by default.** `AGENT_BUDGET_MAX_INPUT_TOKENS` unset → `degrade`
  returns every chunk untouched and does not even pay to measure them. That is
  what keeps this phase behaviour-free, and it is asserted directly.

### `rag/generator.py` folded into the runtime
No module in `rag/` constructs an Anthropic client any more except
`agent_runtime.py`. `verify_phase2.py` greps for a regression.

### `api/routes/query.py`
Down to HTTP concerns: request identity, root LangSmith span, plan-failure →
status code, response assembly, background tasks. It injects
`retrieve_with_project` and the two grounding thresholds into the Manager.

### Runtime (additive, no behaviour change)
`run_agent` gained a `model=` override and `RuntimeResult` gained `latency_ms`.

### Tests — 80 new, zero existing files edited
`test_agent_manager.py` (23), `test_generator_runtime_fold.py` (19),
`test_query_manager_wiring.py` (16), `test_agent_budget.py` (13),
`test_agent_artifacts.py` (9). The wiring file covers the route↔Manager seam —
plan-failure → status-code mapping and the observer adapter that has to
reproduce the pre-Phase-2 LangSmith spans exactly — which neither of the other
two layers' tests reach.

## The four generator traps — what was decided

**(a) The Ollama branch.** `run_agent` is Anthropic-only, so
`LLM_PROVIDER=ollama` still routes to `_generate_with_ollama` and never touches
the runtime. Tested: with the local provider selected, the recorder standing in
for `run_agent` records zero calls.

**(b) Double tracing.** `@traced("answer_generator")` came off `generate_answer`
— `run_agent` records the step now, and keeping both would double-count every
call, exactly as `design_intent` did in Phase 1. But **deleting it outright
would have silently un-traced the Ollama path**, which the runtime never sees.
So the decorator moved onto `_generate_with_ollama`. One step per call on both
branches; both halves have a test.

**(c) `LLM_MODEL` — the one that would actually have shipped a regression.**
It is set in prod: `terraform/main.tf:364` → `claude-haiku-4-5-20251001`.
Letting the tier ladder pick would have moved generation from haiku to
`claude-sonnet-5` — a different model *and* roughly 3x the generation cost —
inside the one phase that forbids behaviour changes, and RAGAs would have
attributed the resulting faithfulness delta to the Manager abstraction.
**Decision: `LLM_MODEL` wins.** `run_agent` gained an explicit `model=` override
and the generator passes the env-resolved id. The tier is still declared
(`Tier.MID`, matching the registry spec) so the ladder's opinion is recorded,
but the override is what goes on the wire. Phase 4 drops the override and hands
model choice to the Budget Governor.

**(d) `max_tokens=1024`.** Left exactly as it was, with a test asserting it is
still 1024 and a docstring explaining why. It will truncate `diy` and
`hiring_contractor` once Phase 4's persona fragments land; that is Phase 4's fix.

**Caching, set deliberately rather than by accident.** `cache_system` is bound to
the existing `ANTHROPIC_PROMPT_CACHE_ENABLED` switch (default off) so the
operator-facing knob keeps its meaning, and the runtime's measurement is the
second gate. The ~400-token system prompt is far below the 4096 floor, so this
is a no-op today either way — it starts mattering in Phase 4.

## Findings worth keeping

1. **The gate test pins route internals, and that dictated the Manager's shape.**
   `test_query_answer_route.py` patches `rag.generator.generate_answer` as a
   *module attribute*; `test_sprint8.py` patches
   `api.routes.query.retrieve_with_project` and the module-level
   `MIN_GROUNDED_CHUNKS` / `MIN_GROUNDED_TOP_SIM`. So: retrieval and the
   thresholds had to be **injected** by the route (patching the route module is
   where the tests reach), and every other collaborator had to resolve through
   the registry's `lazy()` proxy, which does `getattr(import_module(m), attr)`
   at call time and therefore still sees a monkeypatched attribute. Had the
   Manager imported these eagerly, the patches would have stopped biting and the
   "zero behaviour change" claim would have been unfalsifiable.

2. **Registry delegation is load-bearing, not decorative.** Because the Manager
   goes through `registry.get(name).callable`, the Manager tests swap *specs*
   rather than patching modules. If the Manager ever stopped routing through the
   registry, those stubs would silently never be called — the test would fail.

3. **`generator.py` had TWO inline Anthropic clients, not one.**
   `generate_kickoff_chat_response` also built its own. The brief called
   `generate_answer` "the last remaining call site"; AGENTS.md's rule is
   per-module, so both were folded. Same `LLM_MODEL` override for the same
   reason. `cache_system=False` there deliberately — the kickoff prompt is
   per-project and never a stable cacheable prefix.

4. **The Manager's summary must not touch `passing_chunks`.** First cut called
   it while building the retrieval artifact summary, which runs *before* the
   grounding guard. `test_query_answer_empty_corpus_returns_422` passes a
   `SimpleNamespace` with no such attribute — correctly, since the pre-Phase-2
   route never read it before the empty check. Fixed by counting off `chunks`
   instead. This is exactly the kind of ordering assumption a port smuggles in,
   and the existing test caught it.

5. **Routing through the runtime adds a `count_tokens` round trip per
   generation** that did not exist before. Free in tokens, ~100ms in latency.
   It is inherent to the single-call-site design (it is what makes the cache
   decision measured rather than guessed) and does not affect faithfulness, but
   it is a real change to per-request latency and worth watching on machine B.

6. **One deliberate non-output change: more trace rows.** The Manager writes its
   own deterministic step, so `/query/answer` now records 2 rows where it
   recorded 1. Outputs are identical; telemetry is richer. Called out here
   rather than buried, because a scorecard built on row counts will notice.

7. **`response.content[0].text` → `_extract_text`.** The runtime returns `""`
   for a response with no text block instead of raising `IndexError`. Safer, and
   unreachable in practice, but it is a difference.

## Verification performed (machine A)

- `py -m pytest tests/test_query_answer_route.py -v` → **green, with zero edits
  to its assertions.** `git status tests/` was clean at that point — the file was
  untouched. This is the phase's whole signal.
- `py -m pytest tests/ -q` → **395 passed** (was 315; +80 Phase 2 tests).
- `ruff check` clean on every new and edited file. The one remaining warning in
  `rag/generator.py` is a pre-existing `RUF001` en-dash inside `SYSTEM_PROMPT` —
  deliberately not touched, because editing prompt text is precisely what this
  phase forbids.
- `py scripts/verify_phase2.py --no-db` → **18/18 offline checks**, PARTIAL RUN.
- **Not run here:** the live plan run and RAGAs. Empty DB, no corpus.

## Commit

```
feat: Phase 2 Manager + artifact store + Budget Governor, fold generator into the runtime
```

## Still open at session end

- **The RAGAs half of the Phase 2 gate is UNRUN.** Phase 2 is *not* verified.
- `verify_phase2.py --local` unrun (needs the corpus machine).
- Prod migration 027 status still disputed (Phase 0 loose end).
- `pyproject.toml` anthropic floor still unpushed.
- Phase 3's migration number collides with `027_agent_action_item_dedupe`.

## Machine B block — run these, paste the output back

```powershell
.\.venv\Scripts\Activate.ps1
py scripts/check_migration_details.py --local
py scripts/verify_phase1.py --local
py scripts/verify_phase2.py --local
py -m evaluation.ragas_eval --export
py -m evaluation.eval_guard --baseline <path to the Phase 0 results json>
```

`--export` is mandatory on `ragas_eval`. Without it no file is written and
`eval_guard` compares the baseline against itself and passes — a green run that
proves nothing. Target: **avg faithfulness 0.910, floor 0.85.**

## Prompt for next session

> Read STATE.md, journals/session_20260724_phase2.md, AGENTS.md, and
> docs/agent_architecture.md before touching anything. Restate the current task
> first — AGENTS.md pre-session protocol.
>
> **The two-machine split is the biggest time-waster in this project. Machine A
> (this repo) has an EMPTY database and no `documents/raw/`.** Do not propose
> `verify_phase0/1/2.py` (without `--no-db`), `check_migrations.py`,
> `check_migration_details.py`, `ragas_eval`, `eval_guard`,
> `ingest_documents.py`, or `backfill_*.py` here — all fail regardless of
> `--local`, which forces the dotenv file but cannot conjure a corpus. What works
> here: `py -m pytest tests/ -q` (395, fully mocked), `py -m ruff check
> rag/ tests/`, `py scripts/verify_phase2.py --no-db`. Collect machine-B commands
> into ONE copy/paste block at the END of the session.
>
> **First, close Phase 2.** It is code-complete on machine A but **not
> verified**: the RAGAs half of its gate is unrun. The machine-B block is at the
> end of the Phase 2 journal. Phase 2 must re-baseline to the Phase 0 numbers
> (avg faithfulness 0.910, floor 0.85) via `py -m evaluation.ragas_eval --export`
> then `py -m evaluation.eval_guard --baseline <phase-0 json>`. `--export` is
> mandatory — without it eval_guard silently compares the baseline to itself and
> passes. Do not deploy Phase 2 or describe it as verified until that is clean.
> If faithfulness moved, the suspects in order are: the `count_tokens` round trip
> the runtime added, the `LLM_MODEL` override (confirm the recorded step model is
> still `claude-haiku-4-5-20251001`, not `claude-sonnet-5`), and chunk ordering
> into `_format_chunks_for_prompt`.
>
> **Then Phase 3 — Corpus Metadata Validator + 27-doc backfill + superadmin
> dashboard v1 (action queue).** Its own chat, its own branch (`agents/phase-3`).
>
> **Fix the migration numbering before writing any SQL.**
> `docs/agent_architecture.md` still calls Phase 3's migration
> `027_metadata_validation`, but 027 is already taken by
> `027_agent_action_item_dedupe`. Shift Phase 3 → 028 and cascade (prompt
> fragments → 029, ontology/bids → 030), and update the doc's Files section.
> Note the pre-existing duplicate 026 (`026_agent_traces.sql` +
> `026_design_intent_usage_project_fk.sql`) is recorded, not renamed — both are
> already applied by name on multiple databases.
>
> Phase 3 scope: extend `verification_stage` with `metadata` and
> `verification_result` with `needs_review`; `ingestion/metadata_agent.py`
> (deterministic enum/completeness checks first, LLM only for
> content-vs-metadata agreement and date extraction, every proposal carrying a
> source-chunk citation); `scripts/backfill_document_metadata.py`; and the first
> dashboard slice (action queue + metadata review) gated on `is_superadmin()`.
> Governance is non-negotiable per AGENTS.md: writes go through
> `ingestion/governance.py` only, never auto-supersede, never auto-update on a
> source URL change, failing docs sit in `draft` with a blocking action item.
> The corpus is 27/27 null `effective_date` and 5 docs null on
> `doc_type`/`authority_level` — those are retrieval filters, so this is the
> phase that stops us measuring the wrong thing precisely.
>
> Register the validator through `rag/agents/registry.py`, and remember
> `ingestion/` may import `rag/agent_runtime.py` but nothing else from `rag/`.
> Every model call still goes through `run_agent` — there are currently zero
> inline `anthropic.Anthropic(` constructions in `rag/` and
> `scripts/verify_phase2.py` greps to keep it that way.
>
> Carried over, both machine B: `py scripts/check_migration_details.py` to settle
> the disputed prod 027 status BEFORE any prod DB action (it is a `NOT NULL`
> alter — do not blind-re-apply), and push the `anthropic>=0.104.1` floor in
> `pyproject.toml`.
