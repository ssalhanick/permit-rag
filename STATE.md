# permit_rag — State

_Updated: 2026-07-23 (Agent architecture Phase 0 — trace store)_

## Phase

**Agent architecture, Phase 0 complete.** The trace store exists and records every
model call. Next is Phase 1: `rag/agent_runtime.py` as the single Anthropic call
site, plus the agent registry. Full plan: [docs/agent_architecture.md](docs/agent_architecture.md).

## Blocked on

1. **Migration 026 not yet applied** — code degrades gracefully without it (tracing
   logs a warning and continues), but no rows are written until it runs. Local +
   RDS commands below.
2. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip

## Deliverables checklist

### Phase 0 — trace store (code done this session)

- [x] `db/migrations/026_agent_traces.sql` — `agent_runs`, `agent_steps`,
      `agent_corrections`, `agent_action_items`, `agent_autonomy`, with policy
      ceilings seeded from AGENTS.md governance rules
- [x] `db/client.py` — trace insert/query helpers, action-queue upsert with an
      open-item dedupe index, autonomy set clamped to ceiling in SQL
- [x] `audit/logger.py` (was 0 bytes) — `@traced` / `@traced_run` / `record_step`,
      cache-aware cost math, Sonnet-5 intro pricing with a built-in expiry
- [x] `audit/provenance.py` (was 0 bytes) — corpus-state snapshot per answer
- [x] `audit/anomaly.py` (was 0 bytes) — statistics → action items
- [x] Retrofit: `rag/generator.py::generate_answer`, `rag/design_intent.py`,
      run scope on `api/routes/query.py::query_answer`
- [x] `GenerationResult` now carries cache tokens + `stop_reason` (were computed
      and discarded, leaving cache effectiveness unmeasurable)
- [x] **Cost fix**: reranker-rejected chunks no longer reach the model
- [x] 22 new tests; full suite green (292 passed)

- [x] Migration 026 dry-run against local Docker Postgres inside a rolled-back
      transaction: 5 tables create, 15 ceilings seed, dedupe verified for
      entity-bearing, entity-less, distinct-entity, and re-raise-after-resolve
      cases. **Caught and fixed a dedupe bug** (nullable entity columns skipped
      the unique index) before it could be frozen by deployment.

### Verification (not yet run for real — do first next session)

- [ ] `py scripts/apply_migration.py db/migrations/026_agent_traces.sql` **(local first)**
- [ ] Issue one `/query/answer` call, then confirm rows land in `agent_runs` +
      `agent_steps` with non-zero `cost_usd`
- [ ] Confirm `agent_autonomy` seeded 15 rows and that `set_agent_autonomy`
      refuses a level above `max_level`
- [ ] **Re-baseline RAGAs.** The chunk-leakage fix changes what the model sees,
      so faithfulness/precision will move. That is expected, not a regression —
      capture the new baseline before Phase 2 uses it as its no-change gate.
- [ ] Prod: migration 026 against RDS, then deploy

## Verification commands

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/test_audit_logger.py tests/test_generator_chunk_filter.py -v
py -m pytest tests/test_query_answer_route.py tests/test_sprint8.py -v
py scripts/apply_migration.py db/migrations/026_agent_traces.sql
py -m evaluation.ragas_eval
py -m audit.anomaly --window-hours 24
```

## Next tasks

1. Apply migration 026 **locally**; smoke one query; confirm trace rows
2. Re-baseline RAGAs after the chunk-leakage fix
3. Phase 1 — `rag/agent_runtime.py` + `rag/agents/registry.py`
4. Prod rollout, in this order and not before step 2 passes:
   **022 first (still missing on RDS)**, then 026, then deploy the code

## Migration drift — check before touching any database

`scripts/apply_migration.py` executes a file and records nothing: there is no
`schema_migrations` table and no ordering guard. **`scripts/check_migrations.py`
(new) probes for the artifact each migration creates** and reports corpus size
alongside it. Run it first on any database.

`scripts/check_migration_details.py` (new, **read-only**) goes further and
verifies migration *contents*: whether the applied 026 includes the dedupe fix,
and whether 022's columns were actually backfilled. Safe to point at prod.

Confirmed drift as of this session:

| Database | State |
|----------|-------|
| Local Docker (machine A) | 018–021, 023–026 applied; **022 missing** behind them; **026 is the pre-fix version** (nullable entity columns) so 027 is required. Corpus empty. |
| Machine B local | Unknown — run `py scripts/check_migrations.py --local` |
| Prod RDS | 018–026 applied **including 022**; 026 is almost certainly the pre-fix version → needs 027. Confirm with `check_migration_details.py`. |

**026 reached production unintentionally.** `bootstrap_env` loads `.env` last
with `override=True`, and `ENVIRONMENT=production` selects `.env.production`;
all three dotenv files are gitignored, so the target differs per machine and
`apply_migration.py` gave no indication of where it was writing. It now prints
the target host and profile, and requires the hostname to be typed for any
non-localhost target (`--yes` bypasses for CI; nothing automated calls it).

**`.env.local` does not reliably mean localhost.** On machine B it points at a
campus IP — repointed during remote-debugging work and left that way. So
`--local` forces the file but cannot force the destination; the banner reports
the real host and names the file that supplied it rather than trusting the flag.
`scripts/_db_target.py` holds this resolution logic for both diagnostics and
supports `--database-url='...'` as a one-off override. Canonical local value,
from `.env.local.example`:

```
DATABASE_URL=postgresql://postgres:localdev@localhost:5433/permit_rag
```

Applying 022 to a database that already holds a corpus leaves its new columns
NULL until `scripts/backfill_source_identity.py` runs — the migration alone is
not sufficient there.

### Duplicate migration number 026

`026_agent_traces.sql` and `026_design_intent_usage_project_fk.sql` (from commit
`dc802a9`) share a number; the traces migration should have been 027. Recorded
rather than renamed — both are already applied by name on multiple databases,
and renaming an applied migration is riskier than the duplicate.
`check_migrations.py` probes each independently so neither hides the other. The
dedupe correction is therefore **027_agent_action_item_dedupe.sql**.

All of these migrations are additive (`CREATE TABLE IF NOT EXISTS`, `ADD
COLUMN`), so each is individually low-risk and fast, but the gaps should be
closed deliberately rather than by accident.

The code and the migration are independently safe to ship in either order:
tracing degrades to a log line without the tables (verified), and the tables sit
idle without the code. The thing that is *not* safe to ship blind is the
chunk-leakage fix — it changes what the model sees, so RAGAs must be re-baselined
first.

## Module status

| Module | Current state |
|--------|---------------|
| audit | All three modules implemented (were 0-byte stubs) |
| db | Migration 026 written, **not applied**; trace helpers in client.py |
| rag | generator + design_intent traced; generator drops filtered_out chunks |
| api | `/query/answer` opens a trace run; passes `passing_chunks` |
| prod RDS | 19 docs / 17,159 embedded chunks (no migration 022 or 026 yet) |
| tests | 292 passing |

## Decisions log

| Decision | Choice |
|----------|--------|
| Agent framework | In-house on the Anthropic SDK; Claude Agent SDK only for the browser/form agent |
| Structured outputs | Native `client.messages.parse()` — **not** `instructor`; pydantic already a dep |
| Trace table types | `text` + `CHECK`, not enums, so new agent names never need `ALTER TYPE` |
| Tracing failure mode | Degrade to a log line, never raise — observability is not business logic |
| Autonomy ceilings | Stored in `agent_autonomy.max_level`, clamped in both SQL and the runtime; the dashboard cannot raise them |
| Persona default | `research`, never `diy` — a confident wrong DIY answer is the costliest default failure |
| Optimizer/Crystallizer | Propose-only: PR + human merge |
| Phase order | Trace store first; meta agents train on accumulated history |
| Web Form Navigator | Split into its own final phase (9) so it is droppable without stranding the PDF agent |

## Canonical validation

```powershell
py -m pytest tests/test_audit_logger.py tests/test_generator_chunk_filter.py -v
# Prod corpus smoke: GET https://permits.scottsalhanick.com/api/documents  (not [])
```
