# permit_rag — State

_Updated: 2026-07-24 (Phase 3 code built + mocked-tested on machine A — 436 tests; migration numbering fixed to 028; pending machine-B verification + deploy)_

## Phase

**Agent architecture Phase 3 — CODE BUILT on `agents/phase-3` (machine A),
pending machine-B verification + deploy.** Corpus Metadata Validator (agent #13)
+ 27-doc backfill + superadmin dashboard v1 (action queue + metadata review).
Migration **028** (enum extensions only). Full plan:
[docs/agent_architecture.md](docs/agent_architecture.md).

Phases 0, 1, and 2 are complete and on prod (details in
`journals/session_20260724_phase2.md`). Phase 3 is built but **not yet verified
on the corpus and not deployed** — it needs the machine-B block (apply 028, run
the validator/backfill, confirm the dashboard) before merge to
`deployment/sites`.

> **Migration numbering collision RESOLVED.** Phase 3 → **028**
> (`028_metadata_validation.sql`), Phase 4 → 029, Phase 6 → 030. 027 is
> `027_agent_action_item_dedupe` (applied on prod + machine B); the duplicate
> 026 is recorded, not renamed. `docs/agent_architecture.md` Files section and
> phase headers updated.

## Phase 2 — SHIPPED (summary; detail in journal)

Manager + artifact store + Budget Governor; `/query/answer` ported with zero
behaviour change; `rag/generator.py` folded into `run_agent`. Verified both
halves (machine A 398 tests + `verify_phase2 --no-db` 18/18; machine B
`verify_phase2 --local` 26/26, generator fold behaviour-preserving), merged to
`deployment/sites`, GHA-deployed green 2026-07-24. **The RAGAs faithfulness
number is a corpus/judge signal, not a gate** (judge swings ±0.15 on one query).
Full record: `journals/session_20260724_phase2.md`.

## Phase 3 deliverables — BUILT on machine A (pending machine-B verification)

- [x] **Migration numbering fixed** — Phase 3 → 028, cascade 029/030;
  `docs/agent_architecture.md` updated.
- [x] `db/migrations/028_metadata_validation.sql` — `verification_stage +=
  'metadata'`, `verification_result += 'needs_review'`. Additive, idempotent, no
  new tables. `db/schema.sql` enums updated to match.
- [x] `db/client.update_document_metadata_fields` — writes
  effective_date/doc_type/authority_level/subject_tags (the retrieval-driving
  fields `update_document_admin_fields` deliberately omits).
- [x] `ingestion/governance.py` — `apply_metadata_correction` (the single corpus
  writer for corrected metadata) + `flag_document_for_review` (deduped blocking
  action item; `set_draft` gated — **backfill never drafts a live doc**, that
  would empty retrieval; drafting is the ingest path).
- [x] `ingestion/metadata_agent.py` — agent #13. Deterministic first
  (enum conformance → `fail`; completeness incl. empty subject_tags;
  supersession-family detection, flag-only). One structured `run_agent` call
  (`Tier.MID`) for content-vs-metadata + date extraction. **Every proposal
  carries a source-chunk citation.** Writes nothing directly; `validate_document`
  proposes + files items via governance; `validate_corpus` is the backfill driver.
- [x] Registered `metadata_validator` via `api/main._register_di_agents()`
  (rag/ can't import ingestion/; lazily bound). Roster is 10 specs.
- [x] `scripts/backfill_document_metadata.py` — `_db_target`-safe, dry-run by
  default, `--apply` files items, `--no-llm` skips the paid call, `--report`.
- [x] `api/routes/agents_admin.py` — `/admin/agents` action-items (list/resolve)
  + metadata-review (list/apply). Superadmin-gated. Approve routes through
  `governance.apply_metadata_correction` and writes an `agent_corrections` row.
- [x] `frontend/src/admin/` — `SuperadminRoute` (new frontend guard),
  `AgentDashboardPage`, `ActionQueue`, `MetadataReviewPane` (renders each
  proposal with its citation). `/admin/agents` route + superadmin nav link.
- [x] Tests: `test_metadata_agent.py` (24), `test_agents_admin_routes.py` (10),
  `test_governance_metadata.py` (4). **436 total. Zero existing test files edited.**

## The Phase 3 acceptance gate

### Machine A — PASSED

```powershell
py -m pytest tests/ -q                 # 436 passed (was 398; +38 Phase 3)
py -m ruff check rag/ tests/           # clean on new files
py scripts/verify_phase2.py --no-db    # 18/18, incl. the no-inline-anthropic grep
```

The validator lives in `ingestion/` and every model call goes through
`run_agent`, so `verify_phase2`'s grep still passes (zero inline
`anthropic.Anthropic(` in `rag/`).

### Machine B — NOT YET RUN (needs the corpus)

```powershell
py scripts/check_migration_details.py --local                       # read-only, first
py scripts/apply_migration.py db/migrations/028_metadata_validation.sql
py scripts/backfill_document_metadata.py --local --dry-run --report # no writes
py scripts/backfill_document_metadata.py --local --apply --report   # file items
py -m pytest tests/ -q                                              # 436 still green
```

Acceptance (docs/agent_architecture.md): `effective_date` populated or marked
unextractable **with an action item**; zero null `doc_type`/`authority_level`;
zero empty `subject_tags` after review; every proposal carries a source-chunk
citation; failing docs in `draft` (ingest path only); non-superadmins get 403 on
every `/admin/agents` route (asserted in `test_agents_admin_routes.py`).

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
anthropic floor, the migration-numbering collision) are recorded in the journals,
per AGENTS.md "completed work → journal only."_

1. **Phase 3 machine-B verification not yet run.** The code is built + mocked on
   machine A but the corpus half is untouched: apply migration 028, dry-run then
   `--apply` the backfill, review + approve proposals in the dashboard, confirm
   436 tests still pass. Block is in `journals/session_20260724_phase3.md`.
2. **q6 / Dallas ordinance v1-v2-v3 supersession.** Now *detectable*:
   `detect_supersession_candidates` flags the `city-of-dallas-ordiance-v1/v2/v3`
   family for human review (never auto-supersede). Resolving it is a review
   action in the dashboard; once the supersession is resolved, q6 faithfulness
   should climb off ~0.25.
3. **Eval-harness debt (from the Phase 2 caching bug).** (a)
   `RAGAS_ANSWER_CACHE_ENABLED=false` from the shell does **not** work —
   `bootstrap_env()` `load_dotenv(override=True)` overwrites it; use
   `--no-answer-cache`. (b) `eval_guard`'s default baseline is a cached-era run
   and single-shot RAGAs swings ±0.15 on one query. Before RAGAs gates Phase 3,
   establish a fresh **live** multi-sample baseline. Do not gate on one number.
4. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip.

## Next tasks

1. Run the Phase 3 machine-B block (`journals/session_20260724_phase3.md`): apply
   028, backfill dry-run → `--apply`, confirm 436 tests + `verify_phase2
   --no-db`. Then review/approve proposals in `/admin/agents`.
2. After machine-B verification: merge `agents/phase-3` → `deployment/sites`,
   GHA-deploy (028 is additive/safe), then move Phase 3 README Planned → Completed.
3. Before RAGAs is a Phase 3 quality gate, clear the eval-harness debt (item 3).

## Migration drift — check before touching any database

`scripts/apply_migration.py` executes a file and records nothing: there is no
`schema_migrations` table and no ordering guard. **`scripts/check_migrations.py`
probes for the artifact each migration creates** and reports corpus size.
`scripts/check_migration_details.py` (read-only) verifies migration *contents*.
Safe to point at prod. Run one of these first on any database.

**Migration 028 (`028_metadata_validation.sql`, Phase 3) is written but NOT yet
applied anywhere.** It only adds two enum values (`verification_stage +=
'metadata'`, `verification_result += 'needs_review'`) — additive, idempotent.
Apply on machine B first (block in `journals/session_20260724_phase3.md`), then
prod at deploy.

| Database | State (as last recorded) |
|----------|--------------------------|
| Local Docker (machine A, this repo) | 018–021, 023–026 applied; **022 missing**; 026 pre-fix so 027 required here. **028 not applied. Corpus empty.** |
| Machine B local (`localhost:5433`) | **Confirmed current 2026-07-24** (through 027): dedupe fix present, 022 backfilled, 19 docs. **028 pending.** |
| Prod RDS | **Confirmed current 2026-07-24** (through 027): 026 + dedupe fix (027), dedupe index, 022 backfilled, 19 docs. Do NOT re-apply 027. **028 pending deploy.** |

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
| rag/agents/registry | Roster is 10 specs, all lazily bound (Phase 3 added `metadata_validator` via api DI) |
| rag/agent_runtime | Single Anthropic call site. Phase 2 added a `model=` override + `RuntimeResult.latency_ms` |
| rag/generator | **Folded into the runtime.** No inline Anthropic client remains anywhere in `rag/` |
| rag/design_intent | Folded in Phase 1; contract unchanged |
| ingestion/metadata_agent | **New (Phase 3).** Corpus Metadata Validator (agent #13). Deterministic-first; one structured `run_agent` call; cited proposals; writes nothing (via governance only) |
| ingestion/governance | **Phase 3:** `apply_metadata_correction` (single corpus writer) + `flag_document_for_review` (draft gated by `set_draft`) |
| api/routes/agents_admin | **New (Phase 3).** `/admin/agents` action queue + metadata review; superadmin-gated; approve → governance + correction row |
| frontend/src/admin | **New (Phase 3).** `SuperadminRoute`, `AgentDashboardPage`, `ActionQueue`, `MetadataReviewPane`; `/admin/agents` route |
| audit | `record_step` driven by the runtime; the Manager writes its own deterministic step |
| db | 026/027 trace + autonomy helpers; Phase 3 added `update_document_metadata_fields` |
| api/routes/query | Reduced to HTTP concerns; injects retrieval + grounding thresholds into the Manager |
| tests | **436 passing** (+38 Phase 3) |

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
| **Backfill never drafts (Phase 3)** | `document_status='draft'` is excluded by `match_chunks`, so drafting the 27 null-`effective_date` live docs would empty retrieval. `flag_document_for_review(set_draft=...)` — the backfill passes False (propose only); drafting is the ingest-time path (`draft_on_fail=True`) for brand-new incomplete uploads |
| **Metadata write path (Phase 3)** | Corrected metadata lands in the DB (the corpus's source of truth) via `ingestion/governance.apply_metadata_correction` **only** — the single writer. Sidecars stay gitignored local cache. The validator writes nothing; it files cited `needs_review` proposals |
| **Validator autonomy (Phase 3)** | `apply_metadata_correction` is **not** gated by `enforce_autonomy` — the superadmin approving in the dashboard is the L1 human gate. The runtime ceiling (`metadata_validator/semantic` = L1) governs *auto*-application, which this phase never does |
| Validator registration (Phase 3) | `metadata_validator` registered by `api/main._register_di_agents()` (rag/ can't import ingestion/), lazily bound, `Tier.MID` |

## Canonical validation

```powershell
# Machine A (repo machine) — no DB needed
py -m pytest tests/ -q                                # 436 passed
py -m ruff check rag/ tests/
py scripts/verify_phase2.py --no-db                   # 18/18, incl. anthropic grep

# Machine B (corpus machine) — Phase 3 verification (full block in the journal)
py scripts/check_migration_details.py --local                       # read-only, first
py scripts/apply_migration.py db/migrations/028_metadata_validation.sql
py scripts/backfill_document_metadata.py --local --dry-run --report
py scripts/backfill_document_metadata.py --local --apply --report
# Prod corpus smoke: GET https://permits.scottsalhanick.com/api/documents  (not [])
```
