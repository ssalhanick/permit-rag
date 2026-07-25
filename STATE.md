# permit_rag — State

_Updated: 2026-07-25 (Phase 4 core + query-UX pass DEPLOYED to prod. **Media Curator #17 Slice B1 BUILT + pytest GREEN (machine B)** on `feat/media-curator` — migration 030_media_refs + deterministic diy-only curator + Guardrail source gate + Manager wave-4 wiring + AnswerResponse.media_refs + QueryPage videos section + seed script + tests. Remaining to ship: apply 030 + seed vetted links + diy demo on machine B, then deploy. Phase 3 done + on prod.)_

## Phase

**Agent architecture Phase 4 core — DEPLOYED to prod (2026-07-25).** GHA green;
migration 029 applied on prod RDS; `/api/documents` = 19 (corpus intact →
default-path non-regression confirmed). Prompt Router + versioned fragment library
+ persona-aware `max_tokens` + Guardrail truncation trip + kickoff demotion are
live. `agents/phase-4` merged to `deployment/sites`.

**Query-UX pass — DEPLOYED to prod (2026-07-25).** Merged to `deployment/sites`
(fast-forward, commit `45f4c13`) and GHA-deployed (deploy fires on push; the
commit touches `api/`+`rag/`+`frontend/` so both backend and frontend jobs ran).
**Verified live:** `frontend/ npm run build` clean; the served prod bundle
(`assets/index-*.js`) contains the abstain card (`No confident answer found`),
`persona_nudge`, and `top_k:8`; `/api/documents`=19 (backend healthy). **No
migration** (code + frontend only). _One thing not machine-checkable here: an
interactive click-through behind Cognito login — eyeball a vague query → blue
card, no-persona project → 💡 nudge when convenient._ From prod use, addressed
before Media Curator:
1. A grounding-floor miss (`top_similarity < 0.74` or `< 3` chunks) is now a
   **soft abstain returning 200** with a conversational message (was a 422 red
   error). The Manager sets `abstained` + `abstain_message` instead of raising;
   the route returns a normal `AnswerResponse(abstained=true)` with the retrieved
   chunks, disclaimer, and nudge attached; logged to history as `model="abstained"`
   so the abstain rate is visible. Not a routing issue (guard wave 2, routing wave 4).
2. **`persona_nudge` is now rendered** (💡 banner in `QueryPage.jsx`) and set even
   on an abstain (routing runs on the abstain path for exactly this).
3. **UI `top_k` 5 → 8** so more queries clear the 0.74 floor.

**Phase 3 — SHIPPED and deployed.** Corpus Metadata Validator (agent #13) +
backfill + superadmin dashboard v1, live on prod; migration 028 applied; backfill
`--apply` run; good proposals approved. Details in
`journals/session_20260724_phase3.md`. Phases 0–2 on prod
(`journals/session_20260724_phase2.md`).

> **Migration numbering.** Phase 3 → **028** (applied on prod). Phase 4 → **029**
> (`029_prompt_fragments.sql`, applied on prod RDS + machine B). Phase 6 → 030. 027
> is `027_agent_action_item_dedupe`; the duplicate 026 is recorded, not renamed.

## Phase 4 core deliverables — DEPLOYED (2026-07-25)

- [x] `db/migrations/029_prompt_fragments.sql` — additive/idempotent
  (`ADD COLUMN IF NOT EXISTS`): `projects.experience`, `projects.project_notes`.
  `custom_system_prompt` retained (back-compat read), no longer written.
  **NOT applied on any DB yet.**
- [x] `rag/prompts/` — the versioned fragment library. `__init__.py` loader
  (parses a `<!-- version: N -->` header per file, `Fragment.id =
  dimension:key@version`, `library_version()` digest, `bound_notes()`
  sanitizer/bounder). Fragments as `.md` files: `base` + persona (`diy`,
  `contractor`, `hiring_contractor`, `research`) + 7 jurisdictions + 5 intents +
  2 experience modifiers. Hand-authored; git-tracked; the source of truth.
- [x] `rag/agents/prompt_router.py` (agent #2) — `route(...)` composes
  `base ∥ persona ∥ jurisdiction ∥ intent ∥ experience ∥ project_notes` by
  **lookup, no LLM call**. `research` default (never `diy`); missing fragment
  recorded in `.missing` + logged (Crystallizer signal), never fatal;
  `max_tokens_for(persona, intent)` sizes the ceiling. Registered in the roster
  (`rag/agents/__init__.py`), lazily bound.
- [x] `rag/agents/guardrail.py` (agent #4 slice) — `check_truncation(gen)` files
  a deduped `answer_truncated` action item when `stop_reason == 'max_tokens'`.
  Never raises; `rag/agents/ → db/` is allowed so it writes directly.
- [x] `rag/generator.py` — `generate_answer` takes an optional `routed`
  RoutedPrompt: composed system, persona/intent `max_tokens`, fragment ids to
  the trace. **Un-routed default unchanged** (legacy 1024 fallback), so the eval
  harnesses and `test_generator_runtime_fold` stay green. Kickoff emits bounded
  `notes` (schema changed) not a `custom_system_prompt` blob.
- [x] `rag/agents/manager.py` `_generate` — routes the prompt (`_route_prompt`,
  a deterministic `record_step("prompt_router", ...)` with fragment ids),
  derives intent deterministically (`_derive_intent`), passes `routed=` to the
  generator, and runs the Guardrail truncation trip. Router failure degrades to
  the legacy prompt (never 500s the query). `persona_defaulted` threads to the
  route as `AnswerResponse.persona_nudge` (Clarification nudge).
- [x] `db/client.update_project` + `api/routes/projects.py` + `api/schemas.py`
  learn `experience` / `project_notes`. `rag/project_context.py` surfaces both.
- [x] **Eval hooks:** fragment-versioned traces (`prompt_fragment_ids` populated
  on the answer + router steps); `evaluation/langsmith_eval.run_pipeline` takes a
  `persona` and routes for comparable per-persona experiments;
  `evaluation/persona_checks.py` (deterministic persona-appropriateness — the
  LLM judge is Phase 5). Faithfulness is **measure, not gate** this phase.
- [x] Tests (machine A, mocked): `test_prompt_router.py`, `test_guardrail.py`,
  `test_persona_checks.py`, `test_generator_routing.py`.

### The Phase 4 acceptance gate

**Machine A — PASSED (2026-07-25).** `py -m pytest tests/ -q` → **474 passed**
(was 442; +32 Phase-4). `ruff` clean on all Phase-4 files (the ~15 remaining
`ruff check rag/ tests/` hits are pre-existing — `test_sprint9` SIM nits + the
`SYSTEM_PROMPT` en-dash — none introduced here; **do not "fix" the en-dash**, it
is live prompt text that would perturb the RAGAs baseline). `verify_phase2.py
--no-db` → **18/18**; the roster now shows `prompt_router` + `guardrail`.

**Machine B — PASSED (2026-07-25).** Migration 029 applied. `scripts/persona_demo.py
--local` on "bathroom addition permits in Dallas": three genuinely different
answers, `max_tokens` 2048/640/1792 per persona, **all `stop_reason: end_turn`
(zero truncation)**, fragments composed correctly
(`base ∥ persona ∥ jurisdiction:dallas ∥ intent`), **100% appropriateness** on
all three — `hiring_contractor` emitted its "Questions to ask" + "Red flags"
sections. Acceptance items all met: materially different answers; hiring_contractor
questions+red-flags; missing persona → `research` (unit-tested); no
`diy`/`hiring_contractor` truncation. (Media Curator's zero-unsourced-URL gate is
deferred with the agent.)

**Fresh LIVE RAGAs baseline — recorded (`evaluation/results/ragas_20260725_011651.json`).**
Cache off (every `answer_cache_hit` null → real generation). avg_faithfulness
**0.843**, avg_relevancy 0.982, avg_context_precision 0.693, top_sim avg 0.794.
Per-query faithfulness: q0 0.80 · q1 0.75 · q2 0.94 · q3 1.0 · q4 0.92 · q5 1.0 ·
**q6 0.50**. **Read:** 0.843 is 0.007 under the 0.85 line and it is *entirely* q6
("maximum building height in a residential zone"; its context_precision is a
perfect 1.0, so retrieval was right and the answer/judge disagreed) — the exact
single-query ±0.15 swing. **`ragas_eval` measures the UN-ROUTED path** (it calls
`generate_answer` with no persona, `ragas_eval.py:657`), so this confirms Phase 4
did **not** move default-path faithfulness — the non-regression goal. Faithfulness
is **measure, not gate** this phase; not a blocker. This is the first clean live
baseline (one sample); a future RAGAs *gate* needs 3+ samples to average out q6.

## Phase 2 — SHIPPED (summary; detail in journal)

Manager + artifact store + Budget Governor; `/query/answer` ported with zero
behaviour change; `rag/generator.py` folded into `run_agent`. Verified both
halves (machine A 398 tests + `verify_phase2 --no-db` 18/18; machine B
`verify_phase2 --local` 26/26, generator fold behaviour-preserving), merged to
`deployment/sites`, GHA-deployed green 2026-07-24. **The RAGAs faithfulness
number is a corpus/judge signal, not a gate** (judge swings ±0.15 on one query).
Full record: `journals/session_20260724_phase2.md`.

## Phase 3 deliverables — SHIPPED

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
  proposal with its citation; **proposed values are double-click editable** and
  the edit is what gets written on approve), `DocumentMetadataTable`
  (**read-only corpus metadata view**, Documents tab). `/admin/agents` route +
  superadmin nav link.
- [x] `api/routes/agents_admin.py` — added `GET /admin/agents/documents`
  (read-only corpus metadata, superadmin-gated).
- [x] `rag/agent_runtime.py` — `_dispatch` learns models that 400 on
  `temperature` (Sonnet 5, Opus 4.8, …) and retries without it. See decisions log.
- [x] **Deploy hardening (post-deploy):** `list_action_items` source_agent param
  cast to `::text` (a null agent filter was erroring the Action Queue tab);
  validator `max_tokens` 4096 + short quote-free excerpts + **degrade-to-
  deterministic** on a failed LLM parse (verbose ordinance docs were truncating
  the structured JSON); `-vN` no longer read as a version (PDF-part false flag).
- [x] Tests: `test_metadata_agent.py` (26), `test_agents_admin_routes.py` (12),
  `test_governance_metadata.py` (4), + 2 in `test_agent_runtime.py`. **442 total.**

## The Phase 3 acceptance gate

### Machine A — PASSED

```powershell
py -m pytest tests/ -q                 # 442 passed (was 398; +44 Phase 3)
py -m ruff check rag/ tests/           # clean on new files
py scripts/verify_phase2.py --no-db    # 18/18, incl. the no-inline-anthropic grep
```

The validator lives in `ingestion/` and every model call goes through
`run_agent`, so `verify_phase2`'s grep still passes (zero inline
`anthropic.Anthropic(` in `rag/`).

### Machine B — validator dry-run PASSED

`backfill_document_metadata.py --local --dry-run --report` over the 19-doc
corpus: **19/19 `needs_review`**, cited proposals, zero drops, zero supersession
false-flags. Two `effective_date` proposals landed correct at high confidence
(`texas-accessibility-standards` / `ADA-Standards` → 2012-03-15, 0.95 / 0.75).
Migration 028 dry-run validated. The `--apply` run + dashboard approvals are the
operational tail (punch list).

### Prod — dashboard DEPLOYED

`/admin/agents` is live and superadmin-gated (Action Queue, Metadata Review,
Documents). Deployed via `deployment/sites`. **Pending on prod:** apply 028, run
the backfill `--apply`, approve proposals (punch list items 1–3).

Acceptance (docs/agent_architecture.md): every proposal carries a source-chunk
citation ✔; non-superadmins get 403 on every `/admin/agents` route ✔ (asserted
in `test_agents_admin_routes.py`); `effective_date` populated-or-flagged, zero
empty `subject_tags`, and failing-docs-in-draft are satisfied **once the prod
approvals run** — the mechanism ships; the corpus values are corrected through it.

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
anthropic floor, the migration-numbering collision, **the Phase 3 operational
tail — 028 applied on prod, backfill `--apply` run, good proposals approved
2026-07-24**) are recorded in the journals, per AGENTS.md "completed work →
journal only." **Phase 3 is fully done.**_

1. **`checksum_sha256` missing on all 19 docs.** Flagged by the validator's
   completeness check but not proposable (a checksum is the file bytes, not
   content). Needs a separate source-identity backfill, not this agent.
2. **q6 / Dallas ordinance — NOT a supersession.** Corrected on machine B:
   `city-of-dallas-ordiance-v1/v2/v3` are **parts of one oversized PDF** split
   for ingestion, not competing versions. The Phase 2 "supersession" framing was
   wrong. `detect_supersession_candidates` no longer flags `-vN` families (that
   was a false flag); it keys only on the `-YYYYMMDD` re-scrape datestamp. q6's
   real weakness is retrieval spanning the three parts — a retrieval/reranker
   concern, not governance. Not this phase's target.
3. **Eval-harness debt (from the Phase 2 caching bug).** (a)
   `RAGAS_ANSWER_CACHE_ENABLED=false` from the shell does **not** work —
   `bootstrap_env()` `load_dotenv(override=True)` overwrites it; use
   `--no-answer-cache`. (b) `eval_guard`'s default baseline is a cached-era run
   and single-shot RAGAs swings ±0.15 on one query. Before RAGAs gates any phase,
   establish a fresh **live** multi-sample baseline. Do not gate on one number.
4. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple roundtrip.

## Next tasks

1. **Media Curator (#17) — verify + ship Slice B1, then build B2.**
   - **B1 BUILT** on `feat/media-curator` (curated `media_refs` table path, $0, no
     runtime change): migration `030_media_refs.sql`, `db.client.fetch_media_refs`
     /`insert_media_ref`, `rag/agents/media.py` (diy-only, keyword task-map),
     `guardrail.check_media_sources` (zero-unsourced-URL gate), Manager wave-4
     wiring (`_curate_media` ∥ `_generate`), `AnswerResponse.media_refs`,
     `QueryPage.jsx` videos section, `scripts/seed_media_refs.py` + seed JSON,
     tests. Plan: `docs/plan_media_curator.md`.
     **To ship:** (a) ~~pytest~~ **GREEN on machine B (2026-07-25)**;
     (b) machine-B apply `030`, replace the placeholder URLs in
     `scripts/media_refs_seed.json` with vetted links, `seed_media_refs.py --local
     --apply --verified`, run a diy query end-to-end; (c) merge to
     `deployment/sites` + GHA-deploy (backend+frontend; migration 030 by hand on
     prod RDS first).
   - **B2 (deferred):** the `web_search` youtube-only path. Needs the `claude-api`
     skill (tool id) + `run_agent` learning `tools=` + a `web_search_tool_result`
     parser + Budget-Governor cap. Same Guardrail gate. See `docs/plan_media_curator.md`.
   _(Query-UX pass done + deployed 2026-07-25. Still deferred: the full chat-thread
   `QueryPage` redesign, owner chose quick-wins first.)_
2. **Multi-sample live RAGAs baseline** before RAGAs gates any phase (punch 3).
   The 2026-07-25 run (`ragas_20260725_011651.json`, avg 0.843) is the first clean
   *live* one — but one sample; q6 (0.50) alone drags the mean past 0.85. Run 3+
   and average, and repoint `eval_guard`'s default baseline off the stale
   cached-era `ragas_20260531` file. Not a Phase 4 blocker.
3. **Pre-existing, not Phase 4:** q6 (building height) + q1 (electrical)
   faithfulness; the `NLI inference failed ('type')` classifier warning (falls
   back to keyword rules, non-fatal); q6/Dallas 3-part-PDF retrieval weakness.

## Migration drift — check before touching any database

`scripts/apply_migration.py` executes a file and records nothing: there is no
`schema_migrations` table and no ordering guard. **`scripts/check_migrations.py`
probes for the artifact each migration creates** and reports corpus size.
`scripts/check_migration_details.py` (read-only) verifies migration *contents*.
Safe to point at prod. Run one of these first on any database.

**Migration 029 (`029_prompt_fragments.sql`, Phase 4)** adds two nullable columns
to `projects` (`experience`, `project_notes`) via `ADD COLUMN IF NOT EXISTS` —
additive, idempotent, no data migration. Applied on machine B + prod. Safe to
apply anytime; the Router reads the new columns but tolerates them being NULL.

**Migration 030 (`030_media_refs.sql`, Media Curator B1)** `CREATE TABLE IF NOT
EXISTS media_refs` (curated how-to video links) + one partial index. Additive,
idempotent, `text + CHECK` (no enums), `UNIQUE (task_key, url)` for idempotent
seeding. **NOT applied on any DB yet.** Takes the `030` slot; the planned Phase-6
`ontology_and_bids` migration cascades to `031`. Safe to apply anytime; the
Curator tolerates an empty table (returns no videos).

| Database | State (as last recorded) |
|----------|--------------------------|
| Local Docker (machine A, this repo) | 018–021, 023–026 applied; **022 missing**; 026 pre-fix so 027 required here. **028/029/030 not applied. Corpus empty.** |
| Machine B local (campus corpus DB via `.env.local`) | Current through 027; **029 applied 2026-07-25** (Phase 4 demo); 19 docs. **030 pending** (apply for the Media Curator demo). (028 only needed for a local `--apply`.) |
| Prod RDS | **Current through 029 (028 applied 2026-07-24; 029 applied 2026-07-25 at the Phase 4 core deploy).** Backfill `--apply` run; good metadata proposals approved. Query-UX pass added **no** migration. **030 pending** (apply at the Media Curator deploy). Do NOT re-apply 027/028/029. |

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
| rag/agents/manager | Phase 2 orchestrator; **Phase 4:** `_generate` routes the prompt (deterministic `prompt_router` step + fragment ids), derives intent, passes `routed=`, runs the Guardrail truncation trip, threads `persona_defaulted` to the nudge. **Query-UX:** a grounding-floor miss sets `abstained` + `abstain_message` (soft abstain) instead of raising; `_generate` short-circuits (routes for the nudge, skips generation). **Media (B1):** `_route_prompt` persists `resolved_persona`; wave 4 adds `_curate_media` (∥ `_generate`, diy-only, skip on abstain) → Guardrail source gate → `media_refs` threaded through `ManagerResult` |
| rag/agents/artifacts | **New (Phase 2).** `ArtifactRef` + `ArtifactStore`; bounds the Manager's context |
| rag/agents/budget | **New (Phase 2).** Deterministic Budget Governor; uncapped default = no-op |
| rag/agents/registry | Roster is 13 specs, all lazily bound (Media B1 added `media_curator`; Phase 4 added `prompt_router` + `guardrail`; Phase 3 added `metadata_validator` via api DI) |
| rag/prompts | **New (Phase 4).** Versioned fragment library (files + loader). `Fragment.id = dimension:key@version`; `library_version()`, `bound_notes()` |
| rag/agents/prompt_router | **New (Phase 4).** Agent #2. Lookup composition; `research` default; persona/intent `max_tokens`; missing-fragment signal. No LLM call |
| rag/agents/guardrail | **New (Phase 4 slice).** `check_truncation` → `answer_truncated` action item on `stop_reason == 'max_tokens'`. **Media B1:** `check_media_sources` drops any URL not from youtube.com/media_refs (the zero-unsourced-URL gate) → `unsourced_media_url` action item on a drop. Never raises |
| rag/agents/media | **New (Media B1).** Media Curator (agent #17). Deterministic diy-only curator: keyword task-map → `db.client.fetch_media_refs`. Returns `MediaRef` (`sourced=True`); never fabricates a URL. No LLM (B1) |
| rag/agent_runtime | Single Anthropic call site. Phase 3: `_dispatch` learns models that reject `temperature` and retries without it |
| rag/generator | **Folded into the runtime.** Phase 4: takes an optional `routed` RoutedPrompt (composed system + persona `max_tokens` + fragment ids); un-routed default unchanged. Kickoff emits bounded `notes` |
| rag/design_intent | Folded in Phase 1; contract unchanged |
| ingestion/metadata_agent | **New (Phase 3).** Corpus Metadata Validator (agent #13). Deterministic-first; one structured `run_agent` call; cited proposals; writes nothing (via governance only) |
| ingestion/governance | **Phase 3:** `apply_metadata_correction` (single corpus writer) + `flag_document_for_review` (draft gated by `set_draft`) |
| api/routes/agents_admin | **New (Phase 3).** `/admin/agents` action queue + metadata review + read-only `documents`; superadmin-gated; approve → governance + correction row |
| frontend/src/admin | **New (Phase 3).** `SuperadminRoute`, `AgentDashboardPage` (3 tabs), `ActionQueue`, `MetadataReviewPane` (inline-editable proposals), `DocumentMetadataTable` |
| audit | `record_step` driven by the runtime; the Manager writes its own deterministic step |
| db | 026/027 trace + autonomy helpers; Phase 3 added `update_document_metadata_fields`; **Media B1:** `fetch_media_refs` (reader) + `insert_media_ref` (seed writer) |
| api/routes/query | Reduced to HTTP concerns; injects retrieval + grounding thresholds into the Manager. **Query-UX:** `_build_abstain_response` returns a 200 on `plan.abstained`; `_nudge_for` sets `persona_nudge` on both paths. **Media B1:** `_media_ref_responses` maps `plan.media_refs` → `MediaRefResponse` on the success path |
| frontend/src/QueryPage | **Query-UX:** renders `persona_nudge` (💡 banner) + abstains as a calm info card (not a red error); `top_k` 5→8. **Media B1:** "📺 How-to videos" section (renders only when `media_refs` non-empty) |
| evaluation | Phase 4: `langsmith_eval.run_pipeline` takes a `persona` (routes + records fragment ids); `evaluation/persona_checks.py` (deterministic appropriateness) |
| tests | **474 passing** through the query-UX pass. **Media B1 adds** `test_media_curator.py` + `check_media_sources` tests in `test_guardrail.py` + manager media tests in `test_agent_manager.py` + `_media_ref_responses` tests in `test_query_answer_route.py` (machine-A pytest count pending an owner run) |

## Decisions log

| Decision | Choice |
|----------|--------|
| Single call site | `rag/agent_runtime.py` owns every model call. As of Phase 2 there are **zero** inline `anthropic.Anthropic(` constructions in `rag/`; `verify_phase2.py` greps for regressions |
| **`LLM_MODEL` vs. the ladder** | `LLM_MODEL` **wins**, passed to `run_agent` as an explicit `model=` override. It is set in prod (`terraform/main.tf`: `claude-haiku-4-5-20251001`); letting the MID rung decide would swap haiku for sonnet — a different model and ~3x the cost. **Phase 4 core keeps the override** (model choice unchanged); dropping it and handing model choice to the Budget Governor is deferred, not done in this pass |
| Generator caching | `cache_system` is bound to the existing `ANTHROPIC_PROMPT_CACHE_ENABLED` switch (default off), set deliberately rather than left to the runtime's default. A no-op today (the ~400-token system prompt is below the 4096 floor), and it starts mattering when Phase 4's fragment library makes the prefix cacheable |
| Generator tracing | `@traced("answer_generator")` moved off `generate_answer` onto `_generate_with_ollama`. `run_agent` traces the Anthropic path; the Ollama path the runtime never sees keeps the decorator. One step per call on both branches, no double-count |
| **`max_tokens` (Phase 4)** | **Now persona/intent-aware** via `prompt_router.max_tokens_for` (contractor 640, research 896, hiring_contractor 1792, diy 2048; verbose intents +bonus; ceiling 4096). The hard-coded 1024 survives only as the un-routed fallback default in `generate_answer`, so the eval harnesses are unchanged. `stop_reason == 'max_tokens'` now trips the Guardrail |
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
| Persona default | `research`, never `diy` — **implemented in `prompt_router` (Phase 4)**; an absent/unknown persona resolves to research and sets `persona_defaulted` (the Clarification nudge) |
| **Fragments are files, not DB rows (Phase 4)** | The library lives in `rag/prompts/fragments/*.md`, git-tracked, each with a `<!-- version: N -->` header. Iteration = edit a file, bump the header; every trace/eval run records the new `dimension:key@version`. Migration 029 touches only `projects` (the two per-project inputs). A DB-backed fragment store would put prompt authoring behind a migration for no gain at this scale |
| **Router degrades, never 500s (Phase 4)** | `manager._route_prompt` catches any router/library error and falls back to the legacy (un-routed) prompt. Prompt composition must never be the reason a query fails |
| **Kickoff demotion (Phase 4)** | The kickoff chat emits bounded `notes` (≤200 tok, `bound_notes`-sanitized, composed LAST) instead of a free-text `custom_system_prompt` blob. The blob column stays for back-compat read; the Router prefers `project_notes` and falls back to it. Voice/rules come from versioned persona fragments, not per-project free text (which was an injection surface and defeated cross-project caching) |
| **Prompt caching still below floor (Phase 4)** | A single composed persona prompt (~base + one persona + small fragments) is still under the 4096-token Haiku/Opus cache minimum, so `cache_read` stays 0 for now — not over-claimed. Caching starts paying off only if the stable prefix grows past the floor. The plumbing (`cache_system`, breakpoint gated on `count_tokens`) is already correct |
| **Eval: measure, don't gate (Phase 4)** | Faithfulness is measured, not gated, this phase: single-shot RAGAs swings ±0.15 and the baseline is stale-cached (punch 3). The `research` default fragment mirrors today's grounding rules so the default path shouldn't move. Fragment-versioned traces + per-persona experiments + deterministic appropriateness checks are the iterate/measure loop; the LLM-judge persona metric is Phase 5 (Evaluator #23) |
| **Grounding miss = soft abstain, not 422 (query-UX)** | A grounding-floor miss (`< min_chunks` or `top_sim < 0.74`) is a valid *outcome*, not a client error — retrieval ran; the system chose not to answer. The Manager sets `state.abstained` + a friendly `abstain_message` instead of raising; the route returns a **200** `AnswerResponse(abstained=true)` (message, retrieved chunks, disclaimer, nudge), logged as `model="abstained"`. **Chosen over dressing up the 422 in the frontend** because the abstain then joins chat history, carries the nudge/disclaimer, and needs no error-string matching. 200 is also safer than the old 422 vs the CloudFront-404-rewrite concern. Retrieval/generation *failures* still raise → 500. `_http_error`'s grounding→422 branch is retained defensively (dead for grounding) |
| **Backfill never drafts (Phase 3)** | `document_status='draft'` is excluded by `match_chunks`, so drafting the 27 null-`effective_date` live docs would empty retrieval. `flag_document_for_review(set_draft=...)` — the backfill passes False (propose only); drafting is the ingest-time path (`draft_on_fail=True`) for brand-new incomplete uploads |
| **Metadata write path (Phase 3)** | Corrected metadata lands in the DB (the corpus's source of truth) via `ingestion/governance.apply_metadata_correction` **only** — the single writer. Sidecars stay gitignored local cache. The validator writes nothing; it files cited `needs_review` proposals |
| **Validator autonomy (Phase 3)** | `apply_metadata_correction` is **not** gated by `enforce_autonomy` — the superadmin approving in the dashboard is the L1 human gate. The runtime ceiling (`metadata_validator/semantic` = L1) governs *auto*-application, which this phase never does |
| Validator registration (Phase 3) | `metadata_validator` registered by `api/main._register_di_agents()` (rag/ can't import ingestion/), lazily bound, `Tier.MID` |
| **`temperature` deprecation (Phase 3)** | The newer generation (Sonnet 5, Opus 4.8, …) 400s on the `temperature` param; Haiku 4.5 still accepts it — so the validator's first `Tier.MID` call failed on machine B. `run_agent._dispatch` now **learns** it: on a "temperature deprecated" 400 it records the model in `_TEMPERATURE_UNSUPPORTED`, retries without the param, and skips it for every later call in the process (one wasted call, once). No hard-coded model list to rot |
| **Media Curator staged B1/B2 (Media)** | `run_agent` has **no `tools=`** today, so the `web_search` path needs a runtime extension. B1 ships the **curated `media_refs` table only** — a deterministic DB lookup, $0, no runtime change — which satisfies the "zero unsourced URLs" gate by construction (every row is vetted). B2 (web_search, youtube-only) is deferred: it needs the `claude-api` skill for the tool id, `run_agent` learning `tools=`, a `web_search_tool_result` parser, and a Budget cap. Deterministic-first, same as the rest of the system |
| **Media source gate ships with the curator (Media)** | `guardrail.check_media_sources` drops any URL not on youtube.com and not carrying a curated-table `sourced=True` marker, filing an `unsourced_media_url` action item on a drop. On the B1 DB path nothing is ever dropped; the gate ships now (like the truncation trip shipped with the Router) so B2's model-emitted URLs have their backstop from day one |
| **Media migration takes 030 (Media)** | `030_media_refs.sql` claims the `030` slot; the planned Phase-6 `ontology_and_bids` cascades to `031` (unshipped, nothing existed at 030). `text + CHECK` (no enum ALTERs), `UNIQUE (task_key, url)` for idempotent seeding. The fragment-vs-DB call is the opposite of Phase 4's: media links are *data* that changes without a code deploy, so a table (not files) is right |

## Canonical validation

```powershell
# Machine A (repo machine) — no DB needed. Phase 4 verification.
py -m pytest tests/ -q                                # prior 442 + Phase-4 tests green
py -m ruff check rag/ tests/ evaluation/
py scripts/verify_phase2.py --no-db                   # 18/18, incl. anthropic grep

# Machine B (corpus machine) — Phase 4
py scripts/check_migration_details.py --local                       # read-only, first
py scripts/apply_migration.py db/migrations/029_prompt_fragments.sql
# 3-persona demo: same question as diy / contractor / hiring_contractor → 3 answers
py -m evaluation.ragas_eval --export --no-answer-cache              # fresh LIVE baseline
# Prod corpus smoke: GET https://permits.scottsalhanick.com/api/documents  (not [])
```
