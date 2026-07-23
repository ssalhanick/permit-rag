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

### Verification (NOT run against a database yet — do first next session)

- [ ] `py scripts/apply_migration.py db/migrations/026_agent_traces.sql`
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

1. Apply migration 026 locally; smoke one query; confirm trace rows
2. Re-baseline RAGAs after the chunk-leakage fix
3. Phase 1 — `rag/agent_runtime.py` + `rag/agents/registry.py`
4. Prod rollout: migration 026 on RDS + deploy

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
