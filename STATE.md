# permit_rag — State

_Updated: 2026-07-24 (Phase 2 shipped — verified both halves, merged + GHA-deployed; prod/machine-B migrations confirmed current; doc health check done ahead of Phase 3)_

## Phase

**Agent architecture Phase 2 — SHIPPED. Phase 3 is the active phase.**
The `/query/answer` chain is ported behind `rag/agents/manager.py` with zero
behaviour change. Phase 2 added **no migration** — code only. Merged to
`deployment/sites` and deployed via GHA (green) on 2026-07-24. Full plan:
[docs/agent_architecture.md](docs/agent_architecture.md). Current branch:
`agents/phase-3`.

Phases 0, 1, and 2 are complete and on prod. Phase 3 is next: Corpus Metadata
Validator + backfill + superadmin dashboard v1.

> **Phase 2 verified and deployed (2026-07-24).** Both halves of the gate closed:
> machine A (398 tests, `test_query_answer_route` unchanged, `verify_phase2
> --no-db` 18/18) and machine B (`verify_phase2 --local` 26/26; generator fold
> shown behaviour-preserving — pre-Phase-2 code scored the RAGAs q6 query *below*
> Phase 2, so the floor miss predates the fold). **The RAGAs faithfulness number
> is a corpus/judge signal, not a Phase 2 gate** — the judge varies ±0.15 on one
> query run-to-run. That, and the fact that the shipped baselines were cached, is
> eval-harness debt carried into Phase 3 (see punch list).

## Phase 2 deliverables — DONE (machine A)

- [x] `rag/agents/manager.py` — agent #1. Intent routing, plan build,
  delegation, result assembly for `/query/answer`. The plan is four ordered
  waves against a hard `MAX_ITERATIONS = 6`. Delegates through the registry, so
  a spec swap re-points the Manager with no code change.
- [x] `rag/agents/artifacts.py` — `ArtifactRef(id, kind, summary, token_count,
  ttl)` + `ArtifactStore`. The Manager's loop holds **refs only**; payloads
  resolve at the delegation boundary and at assembly. This is what bounds ReAct
  context growth, and why the Manager cannot leak chunk text into a prompt.
- [x] `rag/agents/budget.py` — Budget Governor (agent #3), deterministic, not an
  LLM: per-request cap, ladder selection, degradation (sheds lowest-ranked
  chunks, floored at 3). **Uncapped by default** (`AGENT_BUDGET_MAX_INPUT_TOKENS`
  unset) so it is a no-op this phase — that is what keeps Phase 2 behaviour-free.
- [x] `rag/generator.py` folded into `run_agent` — the last inline Anthropic
  call site in `rag/`. Both of the module's clients were folded
  (`generate_answer` **and** `generate_kickoff_chat_response`); the rule is
  per-module, not per-function.
- [x] `api/routes/query.py` reduced to HTTP concerns: request identity, the
  LangSmith root span, plan-failure → status-code mapping, response assembly.
  Retrieval and the two grounding thresholds are **injected** into the Manager.
- [x] `rag/agents/__init__.py` — roster now registers manager, budget_governor,
  answer_generator, permit_classifier, jurisdiction_resolver, conflict_detector,
  mini_rag_conflicts, project_context, design_intent. All lazily bound.
- [x] `rag/agent_runtime.py` — two additive changes: a `model=` override (see
  the decisions log) and `RuntimeResult.latency_ms`.
- [x] Tests: `test_agent_manager.py` (23), `test_generator_runtime_fold.py` (19),
  `test_query_manager_wiring.py` (16), `test_agent_budget.py` (13),
  `test_agent_artifacts.py` (9), `test_eval_guard.py` (+3 cache-guard). **398
  total. Zero existing test files edited.**
- [x] `scripts/verify_phase2.py` — mirrors verify_phase1, with `--no-db`.

## The Phase 2 acceptance gate — CLOSED (both halves)

### Machine A — CLOSED

```powershell
py -m pytest tests/test_query_answer_route.py -v   # green, ZERO edits to its assertions
py -m pytest tests/ -q                             # 398 passed
py -m ruff check rag/ tests/
py scripts/verify_phase2.py --no-db                # 18/18 offline invariants
```

`tests/test_query_answer_route.py` passing **without any change to what it
expects** is the whole signal of this phase. `git status tests/` was clean
before the new files were added — the ported route satisfies the old test as-is.

### Machine B — the RAGAs half, and what it actually showed

```powershell
py scripts/verify_phase2.py --local
py -m evaluation.ragas_eval --export --no-answer-cache   # NOT the env var — see below
py -m evaluation.eval_guard --baseline <the Phase 0 results json>
```

**The generator fold is behaviour-preserving. The RAGAs floor number is not a
usable gate for it — the metric's own run-to-run noise is larger than any
effect the fold could have.** Evidence, from three live single-query runs of q6
("max building height, Dallas") on Phase 2 code (2026-07-24):

| run | faithfulness | cache_hit | stop_reason | answer |
|-----|-------------|-----------|-------------|--------|
| 131002 | 0.600 | None | end_turn | identical |
| 134430 | 0.417 | None | end_turn | identical |
| 134927 | 0.273 | None | end_turn | identical |

The generated answer is **byte-identical across all three** (temperature=0,
deterministic) and **not truncated** (`end_turn`, so trap (d)'s 1024 cap is not
firing). Yet the RAGAs faithfulness judge — itself an LLM decomposing the answer
into claims — scored the same text 0.273 / 0.417 / 0.600. A 0.33 spread on
identical input. So:

- The full-set live run (`ragas_20260724_123849.json`) landed avg 0.7956, below
  the 0.85 floor, **driven almost entirely by q6** (avg without q6 = 0.8676).
- That miss is **not attributable to Phase 2**: generation is deterministic and
  unchanged, and the fold's pass-through of model / max_tokens / cache / prompt
  is unit-tested in `test_generator_runtime_fold.py`.
- q6 is a genuine grounding weakness on `city-of-dallas-ordiance-v3` — the
  v1/v2/v3 supersession the arch doc flags. A **corpus** problem, Phase 3's job.

**Deciding test — RUN, and it exonerates Phase 2.** q6 on the pre-Phase-2
commit `0651620` (cache emptied, live) scored faithfulness **0.250** — *lower*
than any Phase 2 run (0.273 / 0.417 / 0.600). q6's floor failure predates the
fold. The answer body matched; only the heading punctuation differed
(`— Dallas` vs `(Dallas)`), which is `temperature=0` model nondeterminism, not a
fold artifact: in the RAGAs harness both old and new call
`generate_answer(query, result.chunks)` directly and the wire payload (model,
system, user message, max_tokens, temperature) is unchanged by the fold —
`test_generator_runtime_fold.py` asserts exactly those kwargs.

**Conclusion: the generator fold is behaviour-preserving.** Verified by
identical request payload (unit-tested) + matching answer body + q6 failing on
pre-Phase-2 code too. The RAGAs floor number is a corpus/judge signal, not a
Phase 2 signal.

**Two harness traps, both fixed in code (commits `b3213da`, `6bd90ec`):**
1. `RAGAS_ANSWER_CACHE_ENABLED=false` from the shell **does not work** —
   `bootstrap_env()` runs inside the process and `load_dotenv(override=True)`
   overwrites it (`.env.local.example` ships it `true`). A cached run never
   calls `generate_answer`, scores stale 07-21 answer text, and reports 0ms
   generation latency while looking healthy. **Three gate runs passed this way
   before it was caught.** Use `--no-answer-cache`, which argv cannot clobber.
2. `eval_guard` now hard-fails a candidate whose rows are all `answer_cache_hit`
   — same false-pass class as comparing a file to itself.

## Verification — which machine runs what

**This split is the single biggest time-waster in this project. Check it before
proposing any command.**

### Machine A (repo machine) — EMPTY database, no `documents/raw/`

Only these work here. None of them need a database:

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/ -q                          # 398 passed, fully mocked
py -m ruff check rag/ tests/
python -m compileall rag/ api/ audit/ db/
py scripts/verify_phase1.py --no-db             # offline invariants; touches no DB
py scripts/verify_phase2.py --no-db             # offline invariants; touches no DB
```

`--no-db` runs only pure-Python checks and prints **PARTIAL RUN** — a pre-push
smoke test, never proof that a phase is verified.

### Machine B (corpus machine) — everything DB- or corpus-dependent

These **fail on machine A regardless of the `--local` flag**, because `--local`
forces the dotenv file but cannot conjure a corpus: `verify_phase0.py`,
`verify_phase1.py`, `verify_phase2.py`, `check_migrations.py`,
`check_migration_details.py`, `ragas_eval`, `eval_guard`, `ingest_documents.py`,
`backfill_*.py`.

```powershell
py scripts/verify_phase2.py --local             # live Manager plan + trace rows
py scripts/verify_phase2.py --local --no-llm    # skip the paid answer call
py scripts/verify_phase1.py --local             # Phase 1 regression
py scripts/verify_phase0.py --local             # Phase 0 regression
py scripts/check_migration_details.py --local   # settles the disputed prod 027
py -m evaluation.ragas_eval --export --no-answer-cache   # cache off, or it scores stale text
```

`verify_phase2.py --local` drives the real `run_query_plan` against the real
corpus with no server and no Cognito token, then reads back the two trace rows
it wrote (a deterministic, zero-cost `manager` step carrying `react_iterations`
and `artifact_refs`, and a priced `answer_generator` step).

## Verification — PROD

Phase 1 was deployed via GHA and `verify_phase1.py` passed 10/10 against prod
RDS on 2026-07-24, including the live `cache_read_input_tokens > 0` assertion.
Prod runs **anthropic 0.104.1**, which supports the whole runtime; it lacks
`OverloadedError`, so the retry list resolves error classes by name.

**Phase 2 merged to `deployment/sites` and GHA-deployed green (2026-07-24).**
Code-only, no migration. `verify_phase1.py` and `check_migration_details.py`
both passed 10/10 / clean against **prod RDS** the same day: prod has 026 + the
027 dedupe fix + 022 backfilled, 19 docs, "Nothing to do."

**Machine B local DB (`localhost:5433`) — also confirmed current 2026-07-24:**
`verify_phase1.py --local` 10/10 (incl. `cache_read=8163` on the 2nd probe
call); `check_migration_details.py --local` reports the dedupe fix present,
022 backfilled, 19 docs, "Nothing to do."

## Blocked on / needs your attention (punch list)

_Forward-looking only. Resolved items (Phase 2 verification, prod-027, the
anthropic floor) are recorded in `journals/session_20260724_phase2.md`, per
AGENTS.md "completed work → journal only."_

1. **Migration numbering collision — fix before writing any Phase 3 SQL.**
   `docs/agent_architecture.md` still lists Phase 3's migration as
   `027_metadata_validation` (Files section), but `027_agent_action_item_dedupe`
   already exists and is applied on prod + machine B. Shift Phase 3 → **028**,
   prompt fragments → 029, ontology/bids → 030, and update the doc's Files
   section. The pre-existing duplicate 026 (`026_agent_traces.sql` +
   `026_design_intent_usage_project_fk.sql`) is recorded, not renamed — both are
   applied by name on multiple DBs; leave them.
2. **q6 / Dallas ordinance v1-v2-v3 supersession → Phase 3's first corpus
   target.** q6 ("max building height, Dallas") is weakly grounded even at best
   (0.60), sourced from `city-of-dallas-ordiance-v3`. Phase 3's metadata
   validator + supersession detection is what fixes it. It doubles as a built-in
   regression check: if the validator resolves the supersession, q6 faithfulness
   should climb off ~0.25.
3. **Eval-harness debt (surfaced by the Phase 2 caching bug).** Two related:
   (a) `RAGAS_ANSWER_CACHE_ENABLED=false` from the shell does **not** work —
   `bootstrap_env()` `load_dotenv(override=True)` overwrites it. Use
   `--no-answer-cache` (added this session). (b) `eval_guard`'s default baseline
   `ragas_20260531_122639.json` is itself a **cached-era run** that never
   exercised live generation, and single-shot RAGAs swings ±0.15 on one query.
   Before RAGAs is trusted as a Phase 3 gate: establish a fresh **live**
   (`--no-answer-cache`) multi-sample baseline and consider an N-sample averaging
   mode. Do not gate on a single RAGAs number.
4. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip.

## Next tasks

1. Phase 3 — Corpus Metadata Validator + 27-doc backfill + superadmin dashboard
   v1. Own chat, own branch (`agents/phase-3`, already checked out). Fix the
   migration numbering first (punch item 1); q6 (punch item 2) is the first
   corpus to fix.
2. Before RAGAs is used as a Phase 3 quality gate, clear the eval-harness debt
   (punch item 3).

## Migration drift — check before touching any database

`scripts/apply_migration.py` executes a file and records nothing: there is no
`schema_migrations` table and no ordering guard. **`scripts/check_migrations.py`
probes for the artifact each migration creates** and reports corpus size.
`scripts/check_migration_details.py` (read-only) verifies migration *contents*.
Safe to point at prod. Run one of these first on any database.

| Database | State (as last recorded) |
|----------|--------------------------|
| Local Docker (machine A, this repo) | 018–021, 023–026 applied; **022 missing**; 026 pre-fix so 027 required here. **Corpus empty.** |
| Machine B local (`localhost:5433`) | **Confirmed current 2026-07-24**: dedupe fix present, 022 backfilled, 19 docs, "Nothing to do." |
| Prod RDS | **Confirmed current 2026-07-24**: 026 + dedupe fix (027) applied, dedupe index present, 022 backfilled, 19 docs, "Nothing to do." Do NOT re-apply 027. |

**Why target confusion keeps happening.** `bootstrap_env` loads `.env` last with
`override=True`, and `ENVIRONMENT=production` selects `.env.production`; all three
dotenv files are gitignored, so the target differs per machine. `.env.local` does
**not** reliably mean localhost (machine B's points at a campus IP). Any script
that touches a DB must use `scripts/_db_target.py` (`--local` / `--database-url`
/ banner naming the real host + the file that set it / fail-fast reachability),
never a bare `bootstrap_env()`. Canonical local value (`.env.local.example`):

```
DATABASE_URL=postgresql://postgres:localdev@localhost:5433/permit_rag
```

### Duplicate migration number 026

`026_agent_traces.sql` and `026_design_intent_usage_project_fk.sql` share a
number; the traces migration should have been 027. Recorded, not renamed (both
already applied by name on multiple DBs). The dedupe correction is therefore
**027_agent_action_item_dedupe.sql**. All these migrations are additive.

## Module status

| Module | Current state |
|--------|---------------|
| rag/agents/manager | **New (Phase 2).** The ported `/query/answer` chain; refs-only ReAct loop bounded at 6 |
| rag/agents/artifacts | **New (Phase 2).** `ArtifactRef` + `ArtifactStore`; bounds the Manager's context |
| rag/agents/budget | **New (Phase 2).** Deterministic Budget Governor; uncapped default = no-op |
| rag/agents/registry | Roster grew to 9 specs, all lazily bound |
| rag/agent_runtime | Single Anthropic call site. Phase 2 added a `model=` override + `RuntimeResult.latency_ms` |
| rag/generator | **Folded into the runtime.** No inline Anthropic client remains anywhere in `rag/` |
| rag/design_intent | Folded in Phase 1; contract unchanged |
| audit | `record_step` driven by the runtime; the Manager writes its own deterministic step |
| db | 026/027 trace + autonomy helpers; `set_agent_autonomy` clamps in SQL |
| api/routes/query | Reduced to HTTP concerns; injects retrieval + grounding thresholds into the Manager |
| tests | **398 passing** (+83 Phase 2) |

## Decisions log

| Decision | Choice |
|----------|--------|
| Single call site | `rag/agent_runtime.py` owns every model call. As of Phase 2 there are **zero** inline `anthropic.Anthropic(` constructions in `rag/`; `verify_phase2.py` greps for regressions |
| **`LLM_MODEL` vs. the ladder** | `LLM_MODEL` **wins**, passed to `run_agent` as an explicit `model=` override. It is set in prod (`terraform/main.tf`: `claude-haiku-4-5-20251001`); letting the MID rung decide would have swapped haiku for sonnet — a different model and ~3x the generation cost — inside the phase that forbids behaviour changes. Phase 4 drops the override |
| Generator caching | `cache_system` is bound to the existing `ANTHROPIC_PROMPT_CACHE_ENABLED` switch (default off), set deliberately rather than left to the runtime's default. A no-op today (the ~400-token system prompt is below the 4096 floor), and it starts mattering when Phase 4's fragment library makes the prefix cacheable |
| Generator tracing | `@traced("answer_generator")` moved off `generate_answer` onto `_generate_with_ollama`. `run_agent` traces the Anthropic path; the Ollama path the runtime never sees keeps the decorator. One step per call on both branches, no double-count |
| `max_tokens=1024` | **Left alone** in Phase 2. It will truncate `diy`/`hiring_contractor`; persona-aware sizing is Phase 4 |
| Manager context | `ArtifactRef` ids + summaries only. Payloads resolve at the delegation boundary; the loop never holds chunk text |
| Budget Governor default | **Uncapped.** A cap that bites would be a behaviour change; the governor ships wired and traced but inert until `AGENT_BUDGET_MAX_INPUT_TOKENS` is set |
| Manager dependencies | Retrieval and the grounding thresholds are injected by `api/routes/query.py`. `rag/agents/` may not import `api/`, and those knobs are configured there |
| Manager failure signalling | `ManagerError(stage, kind)`, mapped to status codes by the route. Keeps fastapi out of `rag/agents/` while preserving the exact codes and message text |
| LangSmith spans | The Manager announces stage boundaries via a `StepObserver`; the route adapts them to spans. An observer failure is logged, never raised |
| Structured outputs | Native `client.messages.parse()` → `.parsed_output`; **not** `instructor` |
| Model ladder | `Tier(StrEnum)` cheap/mid/top → haiku-4-5 / sonnet-5 / opus-4-8 |
| Prompt caching | Measure with `count_tokens` first; attach a breakpoint only above the model minimum (4096/2048) |
| Token counting | `client.messages.count_tokens` for anything billed. The artifact store's char/4 estimate is for cap decisions only and is never written as usage |
| Anthropic SDK floor | `pyproject.toml` raised to `>=0.104.1`, the version verified on prod |
| Retry error set | Resolved by name via `getattr` — `OverloadedError` does not exist on prod's 0.104.1 |
| Autonomy | Enforced in the runtime, fail-closed to L0; clamped again on read |
| Registry DI | `rag/agents/` never imports commerce/forms/bids; `api/main.py` injects them; callables bind lazily |
| Registry duplicates | `register()` raises on a name clash unless `replace=True` |
| Tracing failure mode | Degrade to a log line, never raise — observability is not business logic |
| Persona default | `research`, never `diy` |

## Canonical validation

```powershell
# Machine A (repo machine) — no DB needed
py -m pytest tests/test_query_answer_route.py -v      # the Phase 2 gate
py scripts/verify_phase2.py --no-db

# Machine B (corpus machine) — needs the corpus + trace tables
py scripts/verify_phase2.py --local
py -m evaluation.ragas_eval --export --no-answer-cache && py -m evaluation.eval_guard --baseline <phase-0 json>
# Prod corpus smoke: GET https://permits.scottsalhanick.com/api/documents  (not [])
```
