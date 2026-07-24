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
- `py -m pytest tests/ -q` → **398 passed** (was 315; +83 Phase 2 tests, incl. the 3 eval_guard cache-guard tests added later this session).
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

## RAGAs gate — what the machine-B runs actually found (2026-07-24, later)

The RAGAs half was run on the corpus machine, and it turned into a lesson about
the harness before it said anything about Phase 2.

**Three cached false-passes first.** The first three "gate" runs all passed
(avg 0.903, 0.896, then a green `eval_guard`) while measuring nothing. Every row
was `answer_cache_hit=True`: on a cache hit `ragas_eval` never calls
`generate_answer`, so it scored answer text cached on 2026-07-21 — before Phase
2 existed — and reported 0ms generation latency the whole time. The cause is the
same `override=True` footgun already in this repo's DB-target notes:
`RAGAS_ANSWER_CACHE_ENABLED=false` exported from the shell is overwritten by
`bootstrap_env()` → `load_dotenv(override=True)`, and `.env.local.example` ships
the flag `true`. The canonical command in README:660 could never have worked.

Fixed in code (commits `b3213da`, `6bd90ec`):
- `ragas_eval --no-answer-cache` — an argv flag dotenv cannot clobber.
- `eval_guard` hard-fails a candidate whose rows are all cache hits (same
  false-pass class as comparing a file to itself), and prints the cached/live
  split otherwise.
- `ragas_eval` now exports `stop_reason` and `answer_preview`, so a faithfulness
  collapse can be told apart from a truncation.
- README:660 corrected to use `--no-answer-cache`.

**The first genuinely live full run failed the floor — and it was one query.**
`ragas_20260724_123849.json`: avg faithfulness **0.7956** (floor 0.85), but avg
**without q6 = 0.8676**. q6 ("max building height, Dallas") collapsed 0.875 (its
cached score) → 0.364 live.

**Then q6 alone, three live runs, settled attribution:**

| run | faithfulness | cache_hit | stop_reason | answer |
|-----|-------------|-----------|-------------|--------|
| 131002 | 0.600 | None | end_turn | identical |
| 134430 | 0.417 | None | end_turn | identical |
| 134927 | 0.273 | None | end_turn | identical |

The generated answer is **byte-identical across all three** (temperature=0) and
**not truncated** (`end_turn` — trap (d)'s 1024 cap is not firing). The RAGAs
faithfulness judge, itself an LLM, scored the same text 0.273 / 0.417 / 0.600.

**Conclusions:**
1. Generation is deterministic and unchanged by the fold. Combined with
   `test_generator_runtime_fold.py`'s pass-through assertions, the generator
   fold is behaviour-preserving.
2. The floor miss is **not attributable to Phase 2** — it is RAGAs judge noise
   (0.33 spread on identical input) plus a real corpus grounding weakness on q6
   (`city-of-dallas-ordiance-v3`, the v1/v2/v3 supersession the arch doc flags).
3. A single RAGAs run cannot verify or refute a code change here: the metric's
   own run-to-run noise on one query exceeds any plausible fold effect. The
   harness needs N-sample averaging to be a trustworthy gate.

**Old-vs-new q6 diff — RAN, fold exonerated.** Pre-Phase-2 code (`0651620`) on
q6, cache emptied, live: faithfulness **0.250** — lower than every Phase 2 run
(0.273 / 0.417 / 0.600). So q6's floor failure predates the fold entirely. The
answer body matched; only the heading punctuation differed (`— Dallas` vs
`(Dallas)`), which is temp=0 nondeterminism, not a fold change: in the RAGAs
harness both old and new call `generate_answer(query, result.chunks)` directly,
and the wire payload is unchanged (asserted in `test_generator_runtime_fold.py`).
**Generator fold: behaviour-preserving.**

**`verify_phase2.py --local` — RAN, 26/26 (machine B, localhost:5433 corpus).**
Live Manager plan end-to-end: real retrieval, generation priced $0.0034 on the
pinned haiku, two trace rows (deterministic/free manager + priced generator),
artifacts carrying no chunk text, and trap (c) confirmed on the wire
(`claude-haiku-4-5-20251001`). The Manager-orchestration half is closed.

Side note from the probe run: `5/5 citations not matched to context` — the
answer cited chunks absent from the retrieved set. Pre-existing generator
behaviour (unverified citations reach the response); catching it is the Citation
Verifier's job in Phase 5, not a Phase 2 regression.

**Phase 2 is verified.** Both gate halves closed. Being merged to
`deployment/sites` for a GHA deploy (code-only, no migration). The
`anthropic>=0.104.1` floor turned out to already be on the deploy branch
(`b5a0285`) — the "not yet pushed" note was stale.

**Carried Phase 0/1 checks — RAN clean on machine B (`localhost:5433`):**
- `verify_phase1.py --local` → 10/10, incl. `cache_read=8163` on the 2nd probe
  call (the live caching guarantee).
- `check_migration_details.py --local` → dedupe fix present (the
  `027_agent_action_item_dedupe` correction), 022 backfilled, 19 docs, "Nothing
  to do." This settled machine B's local Docker.
- **Prod-027 dispute RESOLVED (same day, prod RDS).**
  `$env:ENVIRONMENT="production"; py scripts/check_migration_details.py` against
  RDS reported the dedupe fix + dedupe index present, 022 backfilled, 19 docs,
  "Nothing to do." Prod already has 027 — STATE was right, the 07-23 journal was
  wrong. Do NOT re-apply it (`NOT NULL` alter would error). `verify_phase1.py`
  also passed 10/10 against prod. Prod is a clean baseline for Phase 3's
  migrations.

## Still open at session end

- Phase 2 generator fold: **shown behaviour-preserving** (deterministic answers
  + unit tests); the old-vs-new q6 diff is the last confirming step.
- `verify_phase2.py --local` unrun (needs the corpus machine).
- q6 / Dallas ordinance supersession → Phase 3 corpus ticket.
- RAGAs harness needs multi-sample averaging to be a reliable gate.
- Prod migration 027 status still disputed (Phase 0 loose end).
- `pyproject.toml` anthropic floor still unpushed.
- Phase 3's migration number collides with `027_agent_action_item_dedupe`.

## Machine B block — the two remaining Phase 2 checks

```powershell
.\.venv\Scripts\Activate.ps1
# 1. Prove the generator fold is inert: old vs new q6 answer must match.
Move-Item evaluation/cache/answers.json evaluation/cache/answers.json.bak -Force; git checkout 0651620; py -m evaluation.ragas_eval --query 6; git checkout agents/phase-2; Move-Item evaluation/cache/answers.json.bak evaluation/cache/answers.json -Force
# 2. Manager-orchestration half (live plan + trace rows).
py scripts/verify_phase2.py --local
# Carried Phase 0/1 checks, same session:
py scripts/check_migration_details.py --local
py scripts/verify_phase1.py --local
```

The 0.910 "baseline" and the "must match avg faithfulness 0.910" target are
retired: that number is a single cached score, and we now know the judge varies
±0.15 on one query. Do not gate Phase 2 on a single RAGAs number.

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
> here: `py -m pytest tests/ -q` (398, fully mocked), `py -m ruff check
> rag/ tests/`, `py scripts/verify_phase2.py --no-db`. Collect machine-B commands
> into ONE copy/paste block at the END of the session.
>
> **Phase 2 is shipped** — verified both halves (machine A 398 tests +
> `verify_phase2 --no-db` 18/18; machine B `verify_phase2 --local` 26/26 and the
> generator fold shown behaviour-preserving), merged to `deployment/sites`,
> GHA-deployed green on 2026-07-24. Prod, machine B, and prod migrations are
> confirmed current (026 + 027 dedupe + 022 backfilled). **Do not re-run the
> Phase 2 RAGAs gate as if it were open** — the faithfulness number is a
> corpus/judge signal, not a Phase 2 gate (the judge swings ±0.15 on one query),
> and the q6 weakness that dragged the floor down is a Phase 3 corpus target, not
> a fold regression.
>
> **Phase 3 — Corpus Metadata Validator + 27-doc backfill + superadmin
> dashboard v1 (action queue).** Its own chat, its own branch (`agents/phase-3`,
> already checked out).
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
