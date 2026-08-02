# permit_rag — State

_Updated: 2026-08-01 — bug-triage batch (19 hand-tested findings) worked
through in priority order on `fix/room-scan`, security first. **Security:**
`GET /api/documents` had no auth at all (any caller, authenticated or not,
got the full corpus incl. other users' private/pending docs); separately
`match_chunks` never filtered on the `visibility` column migration 040 added
for exactly this, so a tier-3 private document's content could surface
verbatim in another user's chat answer. Fixed both — auth-gate + a real
per-user scoped listing (`db_client.list_documents_for_user`), plus migration
**045** extending `match_chunks` with the visibility predicate. The
Python-level plumbing for this (`requesting_user_id` threaded from
`api/routes/query.py` down through `manager.py` → `retrieve_with_project`)
already existed and was already correctly used for the project-scoped
mini-RAG path (`match_project_chunks`) — this closed the *other* gap, the
general corpus path, by finishing three hops that had been left disconnected
(`retrieve_with_project` → `retrieve()` → `match_chunks()`). **Migration 045
is code-complete, tests pass on machine A's mocked suite, but has NOT been
RAGAs-verified** — this machine has no corpus. Per the sequential-gating rule
or your usual `retrieve()`/`pipeline.py` retrieval-change discipline, run the
migration + a fresh RAGAs pass on the corpus machine before trusting it in
prod. **Everything else** (830 pytest / 92 frontend `node --test`, ruff +
`npm run build` clean): consolidated 5 duplicated voice-input
implementations into `frontend/src/hooks/useVoiceInput.js`; shipped a real
Document Library (was double-broken — empty for regular users, full corpus
for admins) + a staff petition-review UI (backend was already properly
gated, had zero frontend); fixed the project switcher (`ProjectSwitcher.jsx`
was passing the whole project object where the backend PATCH expects a
plain id string, so switching silently never worked) and a sticky-default
bug in the kickoff project-name field; superadmin project visibility (other
users' projects render inert with owner identity in the dashboard + nav
switcher, not hidden), unifying two previously-inconsistent superadmin
checks into `useIsSuperAdmin`; browser-specific mic-permission-denied
instructions (`MicPermissionHelp.jsx` — no browser exposes a URL a page can
navigate to for its own permission settings, so this is the click-path
instead of the deep link that can't exist); kickoff flow gets a free-form
text/talk entry path (new `POST /projects/kickoff/extract` +
`generate_kickoff_extraction`, same `run_agent()`/`bound_notes()` discipline
as the existing kickoff chat) that pre-fills the existing step wizard for
review — never bypasses it. Full session detail:
`journals/session_20260801.md`. Room-scan-specific work (native AR
presenter, room-design action-bar reorder, commerce/material-prompt fixes,
project-layout tab-strip redesign) split into separate `[ROOMSCAN]`-prefixed
commits per Scott's instruction — not pushed; he pushes the non-roomscan
commits himself._

_Updated: 2026-07-30 — jurisdiction accuracy overhaul, all 5 phases coded +
tested on machine A (662 passing, up from 605; ruff/frontend build clean),
**migrations 037/038 not yet applied, no real boundaries loaded** (needs
machine B): Phase 0 (deployed to prod already — see below) fixed the
`res.municipality`/`res.jurisdiction_id` bug + gave `update_project`
address-change re-resolution; Phase 1 added `rag/jurisdiction_ids.py`
canonicalization (fixed a 4th Fort Worth spelling gap in `prompt_router.py`)
+ `get_jurisdiction_chain` + migration 037 (`match_chunks` filter →
jurisdiction-chain `text[]`, RAGAs re-run still required before this is
safe to ship); Phase 2 added `scripts/load_gis_boundaries.py` (no real city
polygons loaded yet); Phase 3 added `rag/coverage.py` +
`GET /projects/{id}/coverage` + fixed `generator.py`'s hardcoded
Frisco/McKinney fallback list; Phase 4 added the `overlays` table
(migration 038) + `api/routes/overlays.py` petition/approve/reject +
`match_overlay_chunks`, generalizing the Dallas-only historic/conservation
pilot into a real petition workflow (also fixed a pre-existing duplicate
`retrieve_with_project` definition in `rag/retriever.py` while touching that
function); Phase 5 corrected the false Frisco/McKinney coverage claims in
AGENTS.md/README.md and fixed `docs/backlog.md`'s `fort-worth`→`fortworth`
spelling. Full plan: `docs/jurisdiction_and_gis_runbook.md`. No journal
entry written this session — flag for a proper STATE.md/journal close-out
pass once this lands on machine B._

## Phase

**Current: Phase 5 — all 8 components built + green; feedback loop +
dashboard v2 + Citation Verifier #9 + Permit Strategy #11 all DEPLOYED to
prod (2026-07-26).** `py -m pytest tests/ -q` → 587 passed; ruff-clean;
`frontend/ npm run build` clean. **#5 Query Deconstructor deferred** — built
and green on machine A, not merged (needs machine-B validation, see Next
tasks).

1. **Feedback loop** — `033_answer_feedback.sql`; `POST /query/feedback`;
   `AnswerResponse.run_id`; QueryPage 👍/👎 + comment. `tests/test_feedback_route.py` (5).
2. **Performance Review #24** — `evaluation/perf_review.py`, attributes a
   👎 to an agent from the run trace. Batch-driven: `scripts/review_feedback.py`.
   `tests/test_perf_review.py` (7).
3. **Evaluator #23** — `evaluation/agent_eval.py`, per-agent metric contracts;
   a breach files an action item + auto-demotes autonomy. Batch-driven:
   `scripts/run_agent_eval.py`. `tests/test_agent_eval.py` (6).
4. **Citation Verifier #9** — `rag/agents/citation_verifier.py`, deterministic
   token-span match + one batched entailment call on leftovers. Wired into
   `manager.py` wave 5. `tests/test_citation_verifier.py` (6).
5. **Query Deconstructor #5** — `rag/agents/deconstructor.py`, compound →
   sub-questions + gated fan-out. Built, **not deployed**. `tests/test_deconstructor.py` (6).
6. **Permit Strategy #11** — `rag/agents/permit_strategy.py`, permit set +
   pull-order + fee estimate. Wired via `GET /projects/{id}/permit-strategy`.
   `tests/test_permit_strategy.py` (6).
7. **Field Ontology core** — `forms/ontology.py` (new `forms/` package, no
   migration). `tests/test_ontology.py` (8).
8. **Dashboard v2 & Agent Glossary** — `api/routes/agents_admin.py` +
   `frontend/src/admin/` (Scorecard, Glossary, Corrections, Autonomy tabs).
   `tests/test_dashboard_v2_routes.py` (8).

**Deploy status (2026-07-26):** feedback loop + dashboard v2 + #9 + #11 are
live on prod (migration 033 applied on RDS, GHA green; loop verified
end-to-end: 👎 → `review_feedback.py --apply` → attributed correction →
confirmed in the dashboard). Evaluator/Perf Review are batch scripts, not
auto-triggered — run on machine B once feedback/trace volume exists.
Full detail: `journals/session_20260726_phase5.md`,
`journals/session_20260726_phase5_wiring.md`.

**Earlier phases — shipped, deployed, full detail in their journals:**
- **Phase 4** (Prompt Router + fragment library + query-UX pass + Media
  Curator #17) — CLOSED 2026-07-26. `journals/session_20260725_phase4.md`,
  `journals/session_20260726_phase4_close.md`,
  `journals/session_20260725_media_curator.md`,
  `journals/session_20260725_media_half2.md`.
- **Phase 3** (Corpus Metadata Validator #13 + backfill + dashboard v1) —
  SHIPPED 2026-07-24. `journals/session_20260724_phase3.md`.
- **Phase 2** (Manager + artifact store + Budget Governor) — SHIPPED
  2026-07-24, zero behavior change. `journals/session_20260724_phase2.md`.
- **Phase 0-1** (trace store + agent runtime/registry/autonomy) — SHIPPED
  2026-07-24. `journals/session_20260724.md`.

> **Migration numbering.** Phase 3 → **028** (prod). Phase 4 → **029** (prod +
> machine B). Media Curator → **030** + **031** (prod + machine B) + **032**
> (channel crawl, prod). Phase 5 → **033** (`answer_feedback`, applied prod
> 2026-07-26). **Phase 6 (ontology/bids) reserved at 034** (unshipped) — see
> `docs/agent_architecture.md`'s "What the Field Ontology actually is": parts
> 1-3+7 are the already-shipped ontology *core* (`forms/ontology.py`, no
> migration, Phase 5); part 4 (the per-form mapping corpus —
> `form_templates`/`field_mappings`) plus whatever the Bid Evaluator's
> PDF-upload extraction needs is what 034 actually holds. **It is not a slot
> for any table that merely backs an ontology-sourced field** — a mistake
> made once on this branch and corrected (see below). **Query-session
> grouping → 035** (`query_log.session_id`, applied prod 2026-07-28).
> **Room-image metering → 036** (`design_intent_usage.kind`, applied prod,
> see room-scan session). 027 is `027_agent_action_item_dedupe`; the
> duplicate 026 (`026_agent_traces.sql` / `026_design_intent_usage_project_fk.sql`)
> is recorded, not renamed — both already applied by name on multiple DBs.
>
> **Full reservation ledger as of 2026-07-30:** **034** — `034_ontology_and_bids.sql`,
> the real Phase 6 deliverable (`form_templates` + `field_mappings`, schema
> only — the PDF-parsing agent and review dashboard are unbuilt Phase 7
> work). **037-038 — ALREADY COMMITTED**, on branch
> `fixes/jurisdiction-phase-1-5`: `037_match_chunks_jurisdiction_hierarchy.sql`
> (jurisdiction-chain retrieval) and `038_overlays.sql` (historic/conservation/HOA
> overlays). **039** — reserved for FK constraints. **040** — document-upload plan,
> `040_document_visibility.sql`. **041** — document-upload plan,
> `041_user_trust.sql`.
> **042** — contractor marketplace, `042_marketplace_listings.sql`.
> **043** — contractor marketplace, `043_contractor_profiles.sql` (`contractor_profiles`
> + `contractor_licenses`).
> **044** — contractor marketplace, `044_bids_core.sql` (`bids` + `bid_line_items`
> + `labor_rate_benchmarks`).
> **045** — security fix, `045_match_chunks_visibility.sql` (extends `match_chunks`
> with the tier-3 `visibility` predicate migration 040 documented but never
> implemented; **code-complete, NOT yet RAGAs-verified or applied to any real
> DB** — this repo machine has no corpus, see 2026-08-01 header note).
> **Next unclaimed number is 046.**

## Verification — which machine runs what

**This split is the single biggest time-waster in this project. Check it
before proposing any command.**

### Machine A (repo machine) — EMPTY database, no `documents/raw/`

Only these work here. None of them need a database:

```powershell
.\.venv\Scripts\Activate.ps1
py -m pytest tests/ -q                          # fully mocked
py -m ruff check rag/ tests/
python -m compileall rag/ api/ audit/ db/
py scripts/verify_phase1.py --no-db             # offline invariants; touches no DB
py scripts/verify_phase2.py --no-db             # offline invariants; touches no DB
```

`--no-db` prints **PARTIAL RUN** — a pre-push smoke test, never proof a
phase is verified.

### Machine B (corpus machine) — everything DB- or corpus-dependent

These **fail on machine A regardless of `--local`** — it forces the dotenv
file but cannot conjure a corpus: `verify_phase0.py`, `verify_phase1.py`,
`verify_phase2.py`, `check_migrations.py`, `check_migration_details.py`,
`ragas_eval`, `eval_guard`, `ingest_documents.py`, `backfill_*.py`.

```powershell
py scripts/verify_phase2.py --local             # live Manager plan + trace rows
py scripts/verify_phase2.py --local --no-llm    # skip the paid answer call
py scripts/check_migration_details.py --local   # settles disputed migration state
py -m evaluation.ragas_eval --export --no-answer-cache   # cache off, or it scores stale text
```

`verify_phase2.py --local` drives the real `run_query_plan` against the real
corpus with no server and no Cognito token, then reads back the two trace
rows it wrote.

## Blocked on / needs your attention (punch list)

_Forward-looking only. Resolved items are recorded in the journals, per
AGENTS.md "completed work → journal only."_

1. **`checksum_sha256` missing on all 19 docs.** Flagged by the validator's
   completeness check but not proposable (a checksum is the file bytes, not
   content). Needs a separate source-identity backfill, not this agent.
2. **q6 / Dallas ordinance retrieval weakness.**
   `city-of-dallas-ordiance-v1/v2/v3` are parts of one oversized PDF split
   for ingestion, not competing versions — not a supersession
   (`detect_supersession_candidates` keys only on the `-YYYYMMDD` re-scrape
   datestamp). q6's real weakness is retrieval spanning the three parts — a
   retrieval/reranker concern.
3. **Eval-harness debt.** (a) `RAGAS_ANSWER_CACHE_ENABLED=false` from the
   shell does **not** work — `bootstrap_env()`'s `load_dotenv(override=True)`
   overwrites it; use `--no-answer-cache`. (b) Before RAGAs gates any phase,
   establish a fresh **live** multi-sample baseline (current: one sample,
   `ragas_20260725_011651.json`, avg 0.843) — don't gate on one number.
4. **Mobile OAuth deep links (deferred)** — M0-6/M0-7 device Google/Apple
   roundtrip.
5. **Migration 045 (match_chunks visibility fix) needs a RAGAs run on the
   corpus machine before it's trusted.** Code-complete + mocked-tests-green
   only (2026-08-01, this repo machine has no corpus). Run
   `check_migration_details.py --local` first, then `apply_migration.py`,
   then `py -m evaluation.ragas_eval --export --no-answer-cache` and compare
   against the pre-045 baseline — same sequential-gating discipline as the
   chunking-step evals. This is a real security fix (closes a cross-tenant
   private-document leak into chat answers), so don't leave it sitting
   unverified longer than necessary.

## Next tasks

1. **Phase 5 remaining tail:**
   - **#5 Query Deconstructor** — built (machine A green), NOT deployed.
     Manager wave-1 `_deconstruct` + gated fan-out in `_run_retrieval`.
     **Before merging to `deployment/sites`: validate on machine B** — RAGAs
     (`--no-answer-cache`) unchanged + hand-check a few genuinely compound
     queries (e.g. "setback and height for a garage in Plano, and do I need
     an electrical permit?") retrieve better than the single path.
   - **Run the batch/eval loops on machine B** once volume exists:
     `scripts/review_feedback.py`, `scripts/run_agent_eval.py`, and a
     **multi-sample live RAGAs baseline** (punch #3) — the 2026-07-25 run
     (avg 0.843) is one sample; run 3+, average out q6's ±0.15, repoint
     `eval_guard` off the stale `ragas_20260531` baseline.
   - **Deferred Media Curator items** (tracked in `docs/media-curator-plan.md`):
     B2 `web_search` (needs the `claude-api` skill + `run_agent tools=`);
     link liveness → Freshness Watcher #15; `YOUTUBE_PROXY_*` for at-scale
     ingest.
2. **Pre-existing, not phase-blocking:** q6 (building height) + q1
   (electrical) faithfulness; the `NLI inference failed ('type')` classifier
   warning (falls back to keyword rules, non-fatal).
3. **Bidding marketplace, jurisdiction runbook, document uploads — sequenced on one shared branch (2026-07-30).** `feat/bidding-marketplace` is code-complete (contractor profiles/licensing, marketplace browse/listing, structured bids + Bid Evaluator reuse — see `bids/`, `commerce/connectors/`, migrations `042`-`044`) **plus the actual Phase 6 ontology deliverable, `034_ontology_and_bids.sql`** (`form_templates`/`field_mappings` schema, per `docs/agent_architecture.md` — the PDF-parsing agent and review dashboard are still unbuilt Phase 7 work). 681 tests passing (75 new, mocked — no live DB/browser walkthrough yet, this machine's DB is empty). Agreed sequencing: this branch stays put and is not merged/replaced — jurisdiction runbook work (`docs/jurisdiction_and_gis_runbook.md`) continues next **on this same branch**, then document-uploads work after that — a **separate plan Scott is actively revising** as of 2026-07-30 (not runbook Phase 4's overlay/petition system); its own plan doc/asset is forthcoming, not yet in this repo. Whoever picks up jurisdiction next: migrations **037-038 are still free**, confirmed in the numbering note above — no renumbering needed.
4. **Doc health check batch 4 (2026-07-28) — closed.** Sprint 11 (doc
   governance UI) and Sprint 12 (profile dashboard) confirmed shipped via
   code; `docs/backlog.md` re-confirmed still current; `docs/ux_audit_260703.md`
   spot-checked — all 4 P0s fixed. **Remainder, code-verified but not
   re-run live:** sprint11/sprint12 verification checklists; UX audit #6
   (collaborator owner dedupe, unclear), #7 (raw UUID for Add Member,
   confirmed still broken), #18 (`graph_health` ops note, cosmetic); #11,
   #12, #15, #17 not checked (need a live run, not a code read).

## Migration drift — check before touching any database

`scripts/apply_migration.py` executes a file and records nothing: there is
no `schema_migrations` table and no ordering guard.
`scripts/check_migrations.py` probes for the artifact each migration creates
and reports corpus size. `scripts/check_migration_details.py` (read-only)
verifies migration *contents*. Safe to point at prod. Run one of these first
on any database. Each migration file documents its own safety/idempotency in
its header comment (`db/migrations/0NN_*.sql`) — that's the source of truth
per-migration; this table is just current per-database status.

| Database | State (as last recorded) |
|----------|--------------------------|
| Local Docker (machine A, this repo) | 018–021, 023–026 applied; **022 missing**; 026 pre-fix so 027 required here. **028/029/030/031/032/033/035 not applied. Corpus empty.** |
| Machine B local (campus corpus DB via `.env.local`) | Current through 032; 19 docs; 028 applied + backfill `--apply` run 2026-07-26 (approvals pending in `/admin/agents`). **033 (answer_feedback) pending. 035 (session_id) pending.** |
| Prod RDS | **Current through 035** (028/029 Phase 3-4; 030+031+032 Media Curator; 033 answer_feedback applied 2026-07-26; 035 query_log.session_id applied 2026-07-28). Query-UX pass + C2 + semantic-links are code-only. **034 unshipped (reserved, Phase 6).** Do NOT re-apply 027–033/035. |

**Why target confusion keeps happening.** `bootstrap_env` loads `.env` last
with `override=True`, and `ENVIRONMENT=production` selects `.env.production`;
all three dotenv files are gitignored, so the target differs per machine.
`.env.local` does **not** reliably mean localhost (machine B's points at a
campus IP). Any script that touches a DB must use `scripts/_db_target.py`
(`--local` / `--database-url` / banner naming the real host), never a bare
`bootstrap_env()`. Canonical local value (`.env.local.example`):

```
DATABASE_URL=postgresql://postgres:localdev@localhost:5433/permit_rag
```

**Reaching prod RDS from a laptop:** the real DSN is
`postgresql://postgres:<SSM /permit_rag/prod/db_password>@<rds_endpoint>/permit_rag?sslmode=require`
(get the pieces with `terraform output -raw rds_endpoint` / `-raw db_password`).
`ENVIRONMENT=production` on a laptop does **not** reach it — `.env.production`'s
host is the in-VPC `permit-rag-postgres`, a different DB. Use `--database-url`
with the real endpoint for every prod op **except** `apply_migration.py`
(ignores the flag, reads ambient env — fix `.env.production` first). RDS SG
only admits two allowlisted IPs on 5432 (`terraform/main.tf`, campus + home).

**Duplicate migration number 026.** `026_agent_traces.sql` and
`026_design_intent_usage_project_fk.sql` share a number; the traces migration
should have been 027. Recorded, not renamed. The dedupe correction is
`027_agent_action_item_dedupe.sql`.

## Module status

| Module | Current state |
|--------|---------------|
| rag/agents/manager | Phase 2 orchestrator; **Phase 4:** `_generate` routes the prompt (deterministic `prompt_router` step + fragment ids), derives intent, passes `routed=`, runs the Guardrail truncation trip, threads `persona_defaulted` to the nudge. **Query-UX:** a grounding-floor miss sets `abstained` + `abstain_message` (soft abstain) instead of raising; `_generate` short-circuits (routes for the nudge, skips generation). **Media (B1):** `_route_prompt` persists `resolved_persona`; wave 4 adds `_curate_media` (∥ `_generate`, diy-only) → Guardrail source gate → `media_refs` threaded through `ManagerResult`. **Media C2:** `_how_to_fallback` (wave 4) — a diy compliance-abstain retrieves transcripts and, if they clear the looser how-to floor, generates a grounded how-to answer that replaces the abstain (`how_to=True`). **Phase 5: wave 5 `_verify_citations`** — post-generation Citation Verifier (#9), deterministic ($0), surfaces fabricated citations as `ManagerResult.unsupported_citations` |
| rag/retriever | **Media C2:** `retrieve_how_to` — lean transcript retrieval (embed + `match_how_to_chunks`, no compliance rerank/guardrails, no municipality filter). **Document-upload plan, chunking step 1 (2026-07-30):** `RETRIEVAL_HYBRID_ENABLED` defaulted to `true` (was `false`) — the BM25/RRF fusion path already existed, tested, just off. RAGAs on machine B (`ragas_20260730_204646.json`, `--no-answer-cache`): faithfulness 0.860 (target 0.85, ✅), relevancy 0.822 (q4's 0.000 is the pre-existing judge blind-spot on the redirect sentence, not new — see Decisions log, 2026-07-28), context precision 0.641. Net-positive/neutral — chunking step 2 (static context prefix) unblocked per the sequential-gating rule. **Chunking step 2 (2026-07-30):** corpus re-chunked (`ingest_documents --include-existing`) + force re-embedded (`ingestion.embedder --force`) on machine B, then re-run. Faithfulness 0.937 (+0.077, all 7/7 queries improved, none regressed — clean signal), relevancy 0.968 (+0.146, but q4's swing 0.000→1.000 alone accounts for ~0.14 of that — same pre-existing judge blind-spot resolving, not pure model improvement; discounting it, relevancy still improved ~+0.13). Context precision 0.651 (+0.010 average) **hides real per-query volatility**: q0/q1/q2 up substantially (+0.67/+0.38/+0.11), q3/q5/q6 down substantially (-0.28/-0.56/-0.26) — average looks flat only because gains and losses happen to cancel. Plausible mechanism (not confirmed): the prefix is near-identical across every chunk of the same document, which may homogenize embeddings within a document and reduce passage-level discrimination. Faithfulness/relevancy did not suffer on the queries that lost context precision (q5 in fact gained faithfulness 0.882→1.000 same run it lost context precision) — **Verdict: net-positive, user-confirmed 2026-07-30** — faithfulness/relevancy (the metrics closest to actual answer quality) both improved cleanly and neither regressed on the queries that lost context precision, so the mixed context-precision signal was accepted rather than treated as stop-ship. Chunking step 3 (structure-aware splitting) unblocked. **Chunking step 3 (2026-07-31): STOP-SHIP, not net-positive.** Corpus re-chunked + force re-embedded on machine B, RAGAs re-run vs. step 2's baseline. Faithfulness 0.885 (down from 0.937, -0.052) — still clears the fixed 0.85 target but that is not the gate; comparing to the *previous step's* baseline is the whole point of the sequential-gating rule, precisely to catch a decline like this that an absolute-threshold check would hide. Relevancy 0.839 (down from 0.968, -0.129), almost entirely explained by **q0 (setback requirements) newly hitting the hard-zero relevancy blind spot (0.989→0.000)** — the same RAGAs judge artifact documented for q4 in the 2026-07-28 decision, but appearing on a *different* query for the *first time* across all three chunking steps, not a known non-issue. Separately, **q1 (electrical permit) faithfulness dropped 1.000→0.667**, a real, sizeable decline in the metric closest to answer correctness — unlike step 2's mixed signal, which was confined to context precision and never touched faithfulness/relevancy on the queries it affected. Context precision 0.658 (~flat, +0.007) with the same kind of per-query volatility as step 2 (q5 +0.556, q2/q6/q1 down substantially) but that metric isn't the concern here. **Decision:** do not ship with `CHUNK_STRUCTURE_AWARE_SPLITTING_ENABLED` defaulting true. Deploy proceeding with the flag explicitly forced `false` in prod; structure-aware splitting held back as its own follow-up pending investigation of q0's new blind-spot trigger and q1's faithfulness drop. |
| rag/agents/artifacts | **Phase 2.** `ArtifactRef` + `ArtifactStore`; bounds the Manager's context |
| rag/agents/budget | **Phase 2.** Deterministic Budget Governor; uncapped default = no-op |
| rag/agents/registry | Roster lazily bound. **Phase 5 registered** `citation_verifier` (#9, wired), `query_deconstructor` (#5, deferred), `permit_strategy` (#11, wired via `GET /projects/{id}/permit-strategy`) |
| api/routes/projects | Project lifecycle + membership. **Phase 5:** `GET /{id}/permit-strategy` (Permit Strategy #11) — membership-gated, deterministic `plan_permits(use_llm=False)` |
| frontend/src/projects/ProjectDashboardPage | **Phase 5:** "Permit strategy" panel via `fetchPermitStrategy`; shown when the project has non-cosmetic work |
| frontend/src/QueryPage | **Query-UX** persona nudge/abstain; **Media** how-to sections; **Phase 5** 👍/👎 feedback bar + amber "unsupported citations" banner. **2026-07-28:** ReactMarkdown answer rendering, session-grouped sidebar (`session_id`), Enter-to-submit hardening, scroll-to-newest-answer |
| rag/agents/citation_verifier | **Phase 5, #9.** `verify_answer(answer, chunks)` — deterministic token-span match + one batched entailment call on leftovers; never raises |
| rag/agents/deconstructor | **Phase 5, #5.** `deconstruct(query)` — compound → sub-questions; deterministic gate for simple queries |
| rag/agents/permit_strategy | **Phase 5, #11.** `plan_permits(context)` — permit set (mirrors `projectPermitRules.js`), pull-order, fee estimate |
| forms/ontology | **Phase 5.** Field Ontology core: canonical vocabulary + per-field type/validation + source binding. New `forms/` package (AGENTS.md boundary `forms/ → db/, stdlib`) |
| rag/prompts | **Phase 4.** Versioned fragment library. `Fragment.id = dimension:key@version`; `library_version()`, `bound_notes()` |
| rag/agents/prompt_router | **Phase 4.** Agent #2. Lookup composition; `research` default; persona/intent `max_tokens`; no LLM call |
| rag/agents/guardrail | **Phase 4 slice.** `check_truncation` → action item on `stop_reason == 'max_tokens'`. **Media B1:** `check_media_sources` — zero-unsourced-URL gate |
| rag/agents/media | **Media B1.** Media Curator (#17). Deterministic diy-only curator; never fabricates a URL |
| ingestion/transcript | **Media C1.** `fetch_transcript(url)` — YouTube transcript pull (public captions, no API cost) |
| db.client match_chunks / retrieval | **Media C1:** migration 031 scopes `match_chunks` to `content_class='authority'` in SQL (unchanged 3-arg signature); new `match_how_to_chunks` (diy path). **Jurisdiction (037):** `filter_municipality` became a jurisdiction-chain `text[]` (this row predates recording that — 037 is the actual latest signature prior to 045, see that migration's own header). **Security fix (045, 2026-08-01):** added a 4th `requesting_user_id` param + a tier-3 `visibility` predicate in the WHERE clause, closing the gap `match_project_chunks` (040) already closed for the project-scoped mini-RAG path but the general corpus path never got. Threading fix was mostly Python: `retrieve_with_project()` already received `requesting_user_id` and already passed it to `match_project_chunks`, but silently dropped it on its own call to `retrieve()` — `retrieve()` didn't even accept the param. Both fixed; `db_client.match_chunks()` now takes and forwards `requesting_user_id` too. **RAGAs-unverified as of this entry** — see punch list #5. |
| rag/agent_runtime | Single Anthropic call site. `_dispatch` learns models that reject `temperature` and retries without it |
| rag/generator | Folded into the runtime. Optional `routed` RoutedPrompt (composed system + persona `max_tokens` + fragment ids); un-routed default unchanged. **2026-07-28: `PROMPT_VERSION` v1→v3** — rule 7 now requires real markdown lists (was ambiguous "bullet points," rendered as inline `•` in prod); rule 1 forbids a standalone "Limitations" header. `rag/prompts/fragments/base.md` bumped to version 3 in lockstep (shared grounding rules) |
| rag/design_intent | Folded in Phase 1; contract unchanged |
| ingestion/metadata_agent | **Phase 3.** Corpus Metadata Validator (#13). Deterministic-first; one structured `run_agent` call; cited proposals; writes nothing (via governance only) |
| ingestion/governance | **Phase 3:** `apply_metadata_correction` (single corpus writer) + `flag_document_for_review` |
| api/routes/agents_admin | **Phase 3:** action queue + metadata review + read-only documents. **Phase 5 dashboard v2:** `/scorecard`, `/autonomy`, `/runs/{id}/trace`, `/feedback-summary`, `/corrections`. All superadmin-gated |
| frontend/src/admin | **Phase 3:** `SuperadminRoute`, `AgentDashboardPage`, `ActionQueue`, `MetadataReviewPane`, `DocumentMetadataTable`. **Phase 5:** `AgentScorecard`, `AutonomyPanel`, `CorrectionQueue` tabs |
| audit | `record_step` driven by the runtime; the Manager writes its own deterministic step |
| db | 026/027 trace + autonomy helpers; **Phase 3:** `update_document_metadata_fields`; **Media B1:** `fetch_media_refs`/`insert_media_ref`. **Phase 5:** `upsert_answer_feedback`, `answer_feedback_counts`, `list_downvotes_without_review`, `list_agent_corrections`, `confirm_agent_correction`. **2026-07-28:** `insert_query_log`/`get_user_query_history` learn `session_id` |
| api/routes/query | HTTP concerns only; injects retrieval + grounding thresholds into the Manager. **Phase 5:** both response paths carry `run_id`; `POST /query/feedback` upserts a vote. **2026-07-28:** `X-Client-Session-Id` now persisted as `query_log.session_id` (previously parsed for tracing only) |
| evaluation | **Phase 4:** `langsmith_eval.run_pipeline` persona routing; `persona_checks.py`. **Phase 5:** `perf_review.py` (#24), `agent_eval.py` (#23) |
| tests | **662 passing** (machine A, 2026-07-30) — rest of this table not re-verified against jurisdiction-accuracy changes, see 2026-07-30 header |

## Decisions log

| Decision | Choice |
|----------|--------|
| Single call site | `rag/agent_runtime.py` owns every model call. Zero inline `anthropic.Anthropic(` in `rag/`; `verify_phase2.py` greps for regressions |
| **`LLM_MODEL` vs. the ladder** | `LLM_MODEL` **wins**, passed to `run_agent` as an explicit `model=` override. Set in prod (`terraform/main.tf`: `claude-haiku-4-5-20251001`); letting the MID rung decide would swap haiku for sonnet — ~3x the cost |
| Generator caching | `cache_system` bound to `ANTHROPIC_PROMPT_CACHE_ENABLED` (default off). A no-op today (system prompt below the 4096 floor); starts mattering once the fragment library makes the prefix cacheable |
| Generator tracing | `@traced("answer_generator")` moved off `generate_answer` onto `_generate_with_ollama`. `run_agent` traces the Anthropic path |
| **`max_tokens`** | Persona/intent-aware via `prompt_router.max_tokens_for` (contractor 640, research 896, hiring_contractor 1792, diy 2048; ceiling 4096). Hard-coded 1024 survives only as the un-routed fallback. `stop_reason == 'max_tokens'` trips the Guardrail |
| Manager context | `ArtifactRef` ids + summaries only. The loop never holds chunk text |
| Budget Governor default | **Uncapped.** Ships wired and traced but inert until `AGENT_BUDGET_MAX_INPUT_TOKENS` is set |
| Manager dependencies | Retrieval + grounding thresholds injected by `api/routes/query.py`; `rag/agents/` may not import `api/` |
| Manager failure signalling | `ManagerError(stage, kind)`, mapped to status codes by the route |
| LangSmith spans | Manager announces stage boundaries via a `StepObserver`; the route adapts them to spans. Observer failure logs, never raises |
| Structured outputs | Native `client.messages.parse()` → `.parsed_output`; **not** `instructor` |
| Model ladder | `Tier(StrEnum)` cheap/mid/top → haiku-4-5 / sonnet-5 / opus-4-8 |
| Prompt caching | Measure with `count_tokens` first; attach a breakpoint only above the model minimum |
| Token counting | `client.messages.count_tokens` for anything billed |
| Anthropic SDK floor | `pyproject.toml` raised to `>=0.104.1`, verified on prod |
| Retry error set | Resolved by name via `getattr` — `OverloadedError` does not exist on prod's 0.104.1 |
| Autonomy | Enforced in the runtime, fail-closed to L0; clamped again on read |
| Registry DI | `rag/agents/` never imports commerce/forms/bids; `api/main.py` injects them; callables bind lazily |
| Registry duplicates | `register()` raises on a name clash unless `replace=True` |
| Tracing failure mode | Degrade to a log line, never raise — observability is not business logic |
| Persona default | `research`, never `diy` — absent/unknown persona sets `persona_defaulted` (the Clarification nudge) |
| **Fragments are files, not DB rows** | Library lives in `rag/prompts/fragments/*.md`, git-tracked, `<!-- version: N -->` header. Iteration = edit + bump header. A DB-backed store would put prompt authoring behind a migration for no gain at this scale |
| **Router degrades, never 500s** | `manager._route_prompt` falls back to the legacy prompt on any router/library error |
| **Kickoff demotion** | Kickoff chat emits bounded `notes` (≤200 tok, sanitized) instead of a free-text `custom_system_prompt` blob — voice/rules come from versioned fragments, not per-project free text (an injection surface that defeated cross-project caching) |
| **Prompt caching still below floor** | Single composed persona prompt is still under the 4096-token cache minimum, so `cache_read` stays 0 — not over-claimed. Plumbing is correct; pays off once the stable prefix grows |
| **Eval: measure, don't gate** | Faithfulness measured, not gated: single-shot RAGAs swings ±0.15 and the baseline is stale-cached. Fragment-versioned traces + per-persona experiments are the iterate/measure loop |
| **Grounding miss = soft abstain, not 422** | A valid outcome, not a client error. Manager sets `state.abstained` + `abstain_message`; route returns 200 `AnswerResponse(abstained=true)`. Chosen so the abstain joins chat history with nudge/disclaimer and needs no error-string matching. Retrieval/generation *failures* still raise → 500 |
| **Backfill never drafts** | `document_status='draft'` is excluded by `match_chunks`, so drafting incomplete live docs would empty retrieval. Backfill proposes only; drafting is the ingest-time path for brand-new uploads |
| **Metadata write path** | Corrected metadata lands via `ingestion/governance.apply_metadata_correction` **only** — the single writer. Validator writes nothing; it files cited proposals |
| **Validator autonomy** | `apply_metadata_correction` is not gated by `enforce_autonomy` — the superadmin approving in the dashboard is the L1 human gate |
| **`temperature` deprecation** | Sonnet 5 / Opus 4.8 400 on `temperature`; Haiku 4.5 still accepts it. `run_agent._dispatch` learns it per-model at runtime, no hard-coded list |
| **Media Curator staged B1/B2** | `run_agent` has no `tools=`, so `web_search` needs a runtime extension. B1 ships the curated `media_refs` table only — $0, satisfies "zero unsourced URLs" by construction. B2 deferred (needs `claude-api` skill + `tools=` support) |
| **Media source gate ships with the curator** | `guardrail.check_media_sources` drops any URL not on youtube.com / not curated-table-sourced, filing an action item on a drop |
| **Media migration takes 030** | `text + CHECK` (no enum ALTERs), `UNIQUE (task_key, url)` for idempotent seeding. Media links are *data* that changes without a code deploy, so a table (not files) is right — opposite of the fragment-library call |
| **Answer feedback is its own table, not `agent_corrections`** | Answer-level thumbs are high-volume/weak-signal; `agent_corrections` is an *attributed correction*. A thumbs-up isn't a correction. `033_answer_feedback` captures the raw vote; a thumbs-down is what Performance Review #24 later reads with the run trace to write the attributed correction |
| **Phase 5 feedback migration takes 033; Phase 6 → 034** | Phase 5 ships before Phase 6, so `033_answer_feedback` takes it and Phase-6 ontology/bids cascades to 034. The already-deployed `032` file's own comment still reads "cascades to 033" — a deployed migration is never edited, so this note is authoritative over that stale comment |
| **034 is the ontology per-form mapping corpus, not any contractor-marketplace table (corrected 2026-07-30)** | An earlier pass on `feat/bidding-marketplace` built `034_contractor_profiles.sql`, reasoning that a contractor account backs an ontology-sourced field (`contractor.license_number`, `SourceBinding.PROFILE`) and so "fills" the Phase 6 slot. That conflates *related to* the ontology with *is* the ontology's Phase 6 deliverable — the actual reservation is Field Ontology part 4, the per-form mapping corpus (`form_templates`/`field_mappings`, `docs/agent_architecture.md`), unrelated to contractor accounts. Caught when Scott pushed back directly. Fixed: `034_ontology_and_bids.sql` now holds the real schema (`form_templates` + `field_mappings`, no PDF-parsing agent or review dashboard yet — that's Phase 7); `contractor_profiles`/`contractor_licenses` moved to `043_contractor_profiles.sql` |
| **Performance Review #24 is batch-triggered, not on the query path** | Import boundary (`api/` can't import `evaluation/`) + cost budgeting (~$0.03/thumbs-down on opus) both point to batch. Trigger is `scripts/review_feedback.py` over the un-reviewed-down-vote queue, never a synchronous cost on the user's request |
| **Perf Review never silent-blames** | Every review writes an *unconfirmed* `agent_corrections` row; a superadmin confirms attribution. Below `CONFIDENCE_FLOOR=0.6` the row carries no `attributed_agent` — a human assigns blame |
| **Query sessions are custom, not LangChain** | The `session_id` grouping query-history threads is a plain Postgres column + client-generated UUID, unrelated to LangChain's own memory/session abstractions (not used in this codebase — only LangSmith, for tracing, is). The same `session_id` also tags the LangSmith trace for that thread — see `docs/langsmith_session_tracing.md` |
| **q4's 0.000 RAGAs relevancy is a known judge blind spot, not a quality bug (2026-07-28)** | `PROMPT_VERSION` v2 fixed a real prod bug (inline `•` bullets instead of markdown — rule 7 was ambiguous) but exposed a same-day, reproducible A/B regression: q4 ("building permit requirements") scored relevancy 1.000 under `v1` and 0.000 under `v2` twice. Root-caused to the model appending an explicit "consult the City of Plano Building Inspection Department directly" redirect when corpus coverage is partial — RAGAs' `answer_relevancy` metric hard-zeroes anything it reads as noncommittal, regardless of faithfulness or context precision (q4 hit 0.933 faithfulness / perfect citations the same run it scored 0 relevancy). `v3` tried suppressing the standalone "Limitations" header (rule 1) — didn't fix it, proving the header was never the mechanism; the redirect sentence itself is what trips the judge. **Not fixing further:** that redirect sentence is the same pattern as the existing AHJ disclaimer (`_AHJ_DISCLAIMER_TEXT`) — intentional, appropriate caution for a compliance app, not a hedge to prompt away. Treated like q6 in the original baseline: measure, don't gate, on this one query's relevancy score. Full investigation: `journals/session_20260728.md` |
| **Document visibility bulk-vs-single distinction (2026-08-01)** | `GET /documents` (bulk listing) is superadmin-only (`is_superadmin`, not the broader `is_staff`) — "only super users can see the document corpus" was an explicit product call, bulk corpus browsing being the sensitive operation. `GET /documents/{doc_id}` (single lookup by doc_id, e.g. a citation drill-down from an already-received answer) stays on the broader `is_staff` bypass for tier-3 docs — a regular user already implicitly learns a cited doc_id exists from the answer itself, so gating the single-doc-detail route more tightly than the bulk list doesn't add real protection, just friction. |
| **Voice input: one shared hook, not five more patches (2026-08-01)** | 5 independent copy-pasted voice-input implementations had each drifted into a different subset of bugs (hardcoded-blue mic icon with no listening state, inconsistent "no speech" error mapping, a self-contradictory "not supported: no speech detected" message) because `RoomCaptureWeb.js` emitted two different strings for the same no-speech condition and each call site only ever checked one of them. Concrete proof duplication was the actual bug, not just style debt — patching five call sites again would leave the same fragmentation for the next bug. `frontend/src/hooks/useVoiceInput.js` owns the state machine and error mapping once; callers only control what happens with a transcript/error via `onTranscript`/`onError` callbacks. |
| **Kickoff free-form entry pre-fills the wizard, never bypasses it (2026-08-01)** | Confirmed with Scott directly (not the two options originally offered): free-form text/talk isn't a parallel fast-path to project creation — it's AI extraction (`generate_kickoff_extraction`) that pre-fills the *same* step-by-step wizard fields for the user to review and complete. `address_guess` is deliberately plain text, not geocoded — the user still picks a real `AddressAutocomplete` suggestion on step 1, since municipality/lat-lng can't come from raw text. |
| **Kickoff extraction reuses bound_notes(), never a second free-text blob (2026-08-01)** | The existing kickoff chat deliberately emits bounded, sanitized `notes` instead of a free-text system-prompt blob specifically to close an injection surface (see the "Kickoff demotion" decision above). `generate_kickoff_extraction`'s `comments` field is the same kind of free-text output and gets the identical `bound_notes()` treatment — a new LLM entry point is exactly where that discipline is easiest to forget. |

## Canonical validation

Run before any DB-touching change, on the appropriate machine
(see "Verification — which machine runs what" above):

```powershell
# Machine A (repo machine) — no DB needed
py -m pytest tests/ -q
py -m ruff check rag/ tests/ evaluation/
py scripts/verify_phase2.py --no-db                   # 18/18, incl. anthropic grep

# Machine B (corpus machine)
py scripts/check_migration_details.py --local                       # read-only, first
py scripts/apply_migration.py db/migrations/<next-pending>.sql
py -m evaluation.ragas_eval --export --no-answer-cache              # fresh LIVE baseline

# Prod corpus smoke
curl -s https://permits.scottsalhanick.com/api/health
```
