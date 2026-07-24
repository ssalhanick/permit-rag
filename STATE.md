# permit_rag — State

_Updated: 2026-07-24 (Agent architecture Phase 1 — runtime + registry, verified on local)_

## Phase

**Agent architecture Phase 1 — code-complete and verified on local.**
`rag/agent_runtime.py` is the single Anthropic call site; `rag/agents/registry.py`
is the `AgentSpec` registry. Full suite green (315 passed). Phase 1 adds **no
migration** — it is code only. Full plan:
[docs/agent_architecture.md](docs/agent_architecture.md).

Phase 0 (trace store) is complete and was applied to prod RDS on 2026-07-23.
Phase 2 is next: port the existing query chain behind the Manager with zero
behaviour change.

## Phase 1 deliverables — DONE (local)

- [x] `rag/agent_runtime.py` — the single Anthropic call site:
  - Native structured outputs via `client.messages.parse(output_format=Model)`
    → `.parsed_output` (no `instructor`, no JSON-repair retries).
  - Model ladder: `Tier.CHEAP=claude-haiku-4-5`, `MID=claude-sonnet-5`,
    `TOP=claude-opus-4-8`; `output_config={"effort":"low"}` supported.
  - Prompt caching that **measures before it caches** — a `cache_control`
    breakpoint is attached to the system block only when `count_tokens` says it
    clears the model minimum (4096 haiku/opus, 2048 sonnet). Below that it sends
    a plain string, avoiding the silent-no-cache footgun.
  - `count_tokens` pre-flight budgeting (`token_budget` → `BudgetError`). Never
    tiktoken.
  - Automatic tracing via `audit.logger.record_step` — one step per call,
    carrying model, usage, cost, latency, and the resolved autonomy level.
  - **Autonomy enforcement in the runtime** (`resolve_autonomy_level`,
    `enforce_autonomy`): agents absent from `agent_autonomy` default to **L0
    (fail closed)**; a stored level above `max_level` is clamped on read.
  - Retries with exponential backoff on transient Anthropic errors.
- [x] `rag/agents/registry.py` — `AgentSpec` (name, callable, tier,
  parallel_safe, metrics) + `AgentSpecProtocol`; `register`/`get`/`all_specs`;
  `lazy()` binding so the roster enumerates without importing each agent's deps.
- [x] `rag/agents/__init__.py` — rag self-registers `answer_generator` and
  `design_intent` on import (lazy). commerce/forms/bids are NOT imported here —
  `api/main.py` injects those agents at startup (import boundary held).
- [x] `rag/design_intent.py` — inline Anthropic call folded into the runtime
  behind a `DesignIntentParse` pydantic schema; public dict contract unchanged.
- [x] `AGENTS.md` amended — "no inline anthropic calls" now points at
  `rag/agent_runtime.py`; `rag/agents/ → rag/, db/, audit/, stdlib` added.
- [x] Tests: `tests/test_agent_runtime.py` (15), `tests/test_agent_registry.py`
  (8). Cover ladder, cache-decision, fail-closed autonomy, budget, retries,
  error-step tracing, lazy binding, self-registration, boundary.
- [x] `scripts/verify_phase1.py` — mirrors verify_phase0; pure-Python invariants
  + DB autonomy checks + a live 2-call probe that asserts
  `cache_read_input_tokens > 0` on the second call (the caching guarantee).

## Verification — LOCAL

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/test_agent_runtime.py tests/test_agent_registry.py -v
py -m pytest tests/ -q                          # full suite: 315 passed
py scripts/verify_phase1.py --local             # runtime + registry + live probe
py scripts/verify_phase1.py --local --no-llm     # skip the two real haiku calls
```

The live probe in `verify_phase1.py` makes **two** real haiku calls (fractions
of a cent) behind a >4096-token cached prefix, so it can prove caching works.
Needs the trace tables (026/027) and `ANTHROPIC_API_KEY`. `--no-llm` skips it.

## Verification — PROD: not started for Phase 1

Phase 1 is backend code with **no migration**, so the prod path is: run pytest
by hand, merge to `deployment/sites`, let GHA deploy the backend. See the
deploy-command block at the bottom.

## Blocked on / needs your attention (punch list)

1. **Prod migration 027 — confirm state before doing anything.** STATE's prior
   "Prod migration status" note (2026-07-23) said 026+027 were applied to RDS;
   the same-day journal's "still open" list said prod still needed 027. These
   conflict. **Do not blind-apply 027** — it's a `NOT NULL` alter and re-running
   it on an already-fixed table will error. Run the check command first (below)
   and only apply if it reports the fix missing. This is a Phase 0 loose end, not
   a Phase 1 dependency.
2. **Live caching assertion is unverified on this machine** — this repo's DB is
   empty and it has no `ANTHROPIC_API_KEY` wired for a spend. Run
   `py scripts/verify_phase1.py --local` on the **corpus machine** to confirm
   `cache_read_input_tokens > 0`. The unit test proves the *decision* logic; only
   a live call proves the API honours the breakpoint.
3. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip.

## Next tasks

1. Run `py scripts/verify_phase1.py --local` on the corpus machine (live caching).
2. Phase 2 — Manager + artifact store + Budget Governor, porting
   `api/routes/query.py` behind the Manager with **zero behaviour change**
   (`tests/test_query_answer_route.py` and RAGAs must be identical).
3. Confirm/close the prod 027 loose end (punch item 1).

## Migration drift — check before touching any database

`scripts/apply_migration.py` executes a file and records nothing: there is no
`schema_migrations` table and no ordering guard. **`scripts/check_migrations.py`
probes for the artifact each migration creates** and reports corpus size.
`scripts/check_migration_details.py` (read-only) verifies migration *contents*
(whether applied 026 has the dedupe fix; whether 022's columns were backfilled).
Safe to point at prod. Run one of these first on any database.

| Database | State (as last recorded) |
|----------|--------------------------|
| Local Docker (machine A, this repo) | 018–021, 023–026 applied; **022 missing**; 026 pre-fix so 027 required here. **Corpus empty.** |
| Machine B (corpus machine) | Corpus ingested + backfilled; migrations current. Reconfirm with `py scripts/check_migrations.py --local`. |
| Prod RDS | 026 applied 2026-07-23; **027 status disputed — verify before touching** (punch item 1). |

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
| rag/agent_runtime | **New (Phase 1).** Single Anthropic call site: parse, ladder, caching, budgeting, tracing, autonomy, retries |
| rag/agents | **New (Phase 1).** `registry.py` + self-registration of answer_generator, design_intent |
| rag/design_intent | Inline anthropic call folded into the runtime; contract unchanged |
| audit | Three modules implemented in Phase 0; `record_step` now driven by the runtime |
| db | 026/027 trace + autonomy helpers; `set_agent_autonomy` clamps in SQL |
| rag/generator | Still a legacy inline call site — folded into the runtime in Phase 2 |
| api | `/query/answer` opens a trace run; passes `passing_chunks` |
| tests | **315 passing** (+23 Phase 1) |

## Decisions log

| Decision | Choice |
|----------|--------|
| Single call site | `rag/agent_runtime.py` owns every model call; generator folds in at Phase 2 |
| Structured outputs | Native `client.messages.parse()` → `.parsed_output`; **not** `instructor` |
| Model ladder | `Tier(StrEnum)` cheap/mid/top → haiku-4-5 / sonnet-5 / opus-4-8 |
| Prompt caching | Measure with `count_tokens` first; attach a breakpoint only above the model minimum (4096/2048) — never guess, never silently no-cache |
| Token counting | `client.messages.count_tokens`; on failure skip budget + skip caching (no tiktoken guess) |
| Autonomy | Enforced in the runtime, fail-closed to L0; clamped again on read; dashboard only edits `current_level` |
| Registry DI | `rag/agents/` never imports commerce/forms/bids; `api/main.py` injects them; agent callables bind lazily |
| Registry duplicates | `register()` raises on a name clash unless `replace=True` — no silent shadowing |
| Tracing failure mode | Degrade to a log line, never raise — observability is not business logic |
| Trace table types | `text` + `CHECK`, not enums, so new agent names never need `ALTER TYPE` |
| Persona default | `research`, never `diy` |

## Canonical validation

```powershell
py -m pytest tests/test_agent_runtime.py tests/test_agent_registry.py -v
py scripts/verify_phase1.py --local
# Prod corpus smoke: GET https://permits.scottsalhanick.com/api/documents  (not [])
```
