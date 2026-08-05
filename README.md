# permit_rag

RAG-powered construction permit compliance tool for the DFW market.
Contractors and project managers query it to get cited answers from
Dallas, Plano, and Fort Worth municipal codes, plus Texas state and
federal regulations. (Frisco and McKinney are planned but not yet
covered — see [docs/backlog.md](docs/backlog.md).)

---

## Current Status (2026-08-04)

- **Agent performance review + security finding (2026-08-04)** — First review of the live agent architecture since the Phase 5 launch (~1.5 weeks). Fixed a real prompt-instruction gap (`jurisdiction/{frisco,mckinney}.md` claimed local ordinance amendments that don't exist in the corpus). Confirmed migration 045's RAGAs run already happened (2026-08-02, no regression) — corrected the stale "pending" note below — though the actual cross-tenant security property still needs a hand-check, not just a RAGAs number. **Flagged, unresolved: a live prod DB password is committed to git and already pushed to GitHub** (`evaluation/results/reprocess/20260802_101100/`) — see [STATE.md](STATE.md)'s SECURITY section for detail; rotation/remediation is pending. Full detail: `journals/session_20260804_agent_performance_review.md`.
- **Database Migration Parity & System Health Check (2026-08-02)** — Verified migration integrity across migrations `001`–`045` with automated missing-migration detection (`check_migrations.py` scanner + `test_migration_integrity.py` enforcement gate, **832 pytest green**). Fixed unbackfilled `022_source_identity` status reporting in `check_migration_details.py`, seeded RDS labor rate benchmarks (`044_bids_core`), and added clean `atexit` connection pool closing in `db/client.py` to eliminate terminal exit warnings. Updated mobile navigation layout so unauthenticated Sign In/Up buttons stack into vertical column items on mobile viewports.
- **Bug-triage batch + security fix (2026-08-01)** — 19-item hand-test bug list worked through in priority order on `fix/room-scan`. Closed security exposure (`GET /api/documents` auth-gated + `match_chunks` tier-3 `visibility` predicate in migration `045`). Consolidated 5 duplicated voice-input implementations into `useVoiceInput` hook; fixed project switcher; shipped per-user Document Library + staff petition-review UI; superadmin project visibility; and kickoff free-form text/talk entry path. Full detail: `journals/session_20260801.md`.
- **UI & Frontend Navigation Modernization Complete (2026-07-27)** — Full design system alignment (`tt-*` CSS variables, high contrast WCAG 2.0 AA dark/light mode parity) completed across all application pages (`ProfileHistoryPage`, `ProfileRoomScansPage`, `ProjectsPage`, `ProjectDashboardPage`, `DocumentBrowserPage`, `ProjectSettingsPage`, `ProjectMembersPage`, `ProjectQueriesPage`). Implemented global floating `AiAssistantWidget` popover with full-screen query toggle, reorganized navigation header (Documents moved under Administration menu), fixed mobile/tablet centered nav dropdown containment, added SVG favicon (`favicon.svg`) & Apple touch icons, and cleaned up legacy promo banners.
- **Agent architecture Phases 0–4 shipped to prod — Phase 4 CLOSED** — trace store, single-call-site runtime + registry, Manager + artifact store + Budget Governor, and the **Corpus Metadata Validator (agent #13) + backfill + superadmin dashboard v1** (`/admin/agents`: action queue, inline-editable metadata review, read-only Documents view). `/query/answer` runs behind the Manager. **Phase 4 core (Prompt Router + versioned fragment library + persona-aware `max_tokens`) is deployed to prod** (2026-07-25) — one question, three personas, three genuinely different answers — followed by a query-UX pass (grounding-floor miss now a conversational 200 abstain instead of a 422 error, `persona_nudge` rendered, UI `top_k` 5→8). **Media Curator (#17) is fully deployed** (2026-07-25): B1 curated links, C1 transcripts, C2 diy how-to answers, semantic links, and This Old House channel data on prod; channel-crawl / throttle / `sync_how_to_to_prod` ops tooling merged to `deployment/sites` (migration `032`). **Phase 5 (answer agents + Evaluator + feedback loop) code-complete and tested (832 pytest green).** See [docs/agent_architecture.md](docs/agent_architecture.md) and [STATE.md](STATE.md).
- **On-demand URL pull implemented** — admin Pull-from-URL on `/upload`: page crawl, checksum diff, ingest-new / supersede-changed, migration 022 identity keys. Verification checklist pending: [docs/on_demand_url_pull.md](docs/on_demand_url_pull.md).
- **Prod corpus seeded** — RDS has 19 active docs / 17,159 embedded chunks.
- **Sprint 17 wrapped** — Scan → Design → Preview → **Generate image** → Save; AR textures prefer `asset_url` then product photos. See [STATE.md](STATE.md) and [docs/room_generative_preview.md](docs/room_generative_preview.md).
- **Sprint 16 closed** — Commerce overlays, SerpApi HD resolver, materials estimate panel.
- **Sprint 13 closed** — Capacitor 7 mobile shell, mini-RAG, corpus sync, prod on ECS `:11`. See [docs/sprint_13capacitor-implementation-overview.md](docs/sprint_13capacitor-implementation-overview.md).
- **Production** — `https://permits.scottsalhanick.com`; Cognito auth; mobile CORS live.

```bash
# Mobile build + open Xcode (run from repo root)
cd frontend
npm run test
npm run build:mobile
npx cap sync ios
npx cap open ios
# In Xcode: select your iPhone → Product → Run (⌘R)

# First time on a new Mac, if pods fail:
cd ios/App && pod install && cd ../..
```

```powershell
# Backend smoke
.\.venv\Scripts\Activate.ps1
py -m pytest tests/ -v
```

---

## TODO

### In Progress
- [ ] **[Agent Architecture](docs/agent_architecture.md)** — 26-agent roster under one Manager, with prompt routing, a feedback loop, autonomy levels, and a token protocol. **Phases 0–4 are deployed to prod and CLOSED.** **Phase 5 (the course cut line) is CODE-COMPLETE and VERIFIED** — all 8 components built + tested (**832 pytest green**): answer-level feedback loop, Performance Review #24, Evaluator #23, Citation Verifier #9, Query Deconstructor #5, Permit Strategy #11, Field Ontology core, and dashboard v2 (scorecard / corrections confirm-queue / autonomy). **Remaining tail:** deploy (apply migration `033` by hand + GHA), wire the three answer agents into the Manager's live query path, and run the batch eval loops + multi-sample RAGAs baseline on machine B. Phases 0–5 are the demo slice.

### Planned
- [ ] **Step-by-step instructions agent** — agent #12 in [docs/agent_architecture.md](docs/agent_architecture.md); turns project/design-intent context into detailed step-by-step instructions, persona-aware. Backs an "Instructions produced" section on the project dashboard (deferred from migration 023's project lifecycle work — no data source existed yet).
- [ ] Device smoke: Preview → Generate image → Save → AR texture → DXF on iPhone ([docs/room_generative_preview.md](docs/room_generative_preview.md))
- [ ] Optional: set `OPENAI_API_KEY` (+ SSM) for live generative room images (mock PNG works offline)
- [ ] **Sign up for [SerpApi](https://serpapi.com/) account** — required for live Home Depot pricing/inventory (see [Commerce / SerpApi](#commerce--serpapi) below); mock catalog works without it for demos
- [ ] [Sprint 14: 3D Room Capture](docs/sprint_14_3d-room-capture-agnostic-guide.md) — Capacitor plugin, interchange JSON v1.0, on-device metrics → `room_summary` API
*(The former "Agent Implementation Plan" and "Token Optimization & Cost-Effectiveness Plan" entries are superseded by [docs/agent_architecture.md](docs/agent_architecture.md), which absorbs both. Note it drops the planned `instructor` dependency: the Anthropic SDK now has native structured outputs via `client.messages.parse()`, and `pydantic` is already a dependency.)*
- [ ] [CMS Admin Dashboard](.gemini\antigravity\brain\acda4bb1-53b2-4cf2-b710-5e93089c1fab\cms_admin_dashboard_plan.md)
- [ ] [Cognito Groups RBAC](docs/cognito_groups_rbac.md) — Cognito groups as source of truth for `member` / `admin` / `superadmin`; staff bypass for see-everything; keep project_members + ops token

### Upcoming
- [ ] **CI: pytest gate on deploy** — add a `pytest` job to `.github/workflows/deploy.yml` that `deploy-backend` depends on, so a failing suite blocks the deploy. Today the workflow runs only `python -m compileall` (syntax), not the 832-test suite, so a compiling-but-failing commit can ship to prod. (Migrations stay manual — CI has no RDS reach.)
- [ ] **SerpApi production key** — add `SERPAPI_API_KEY` to ECS task env / SSM after account signup (blocker for live HD prices; mocks work until then)
- [ ] Add ability to update existing documents
- [ ] Mobile OAuth deep links (M0-6/M0-7) + Firebase push (`google-services.json`)
- [ ] Terraform: fix RDS `DATABASE_URL` drift or move to SSM before next `terraform apply`
- [ ] 3D Map Integration — CesiumJS city boundaries + site overlay

### Completed
- [x] **Database Migration Ledger & System-wide Health Check (2026-08-02)** — Automated missing-migration probes scanner in `check_migrations.py` + `test_migration_integrity.py` CI enforcement gate; fixed unbackfilled document query logic for migration 022 in `check_migration_details.py`; seeded labor rate benchmarks; registered `atexit` pool cleanup in `db/client.py` to eliminate process termination warnings; fixed unauthenticated mobile nav sign-in button alignment. **832 backend pytest green**.
- [x] **Bug-triage batch + document security fix (2026-08-01)** — worked through a 19-item hand-tested bug list on `fix/room-scan`, split general-site fixes from room-scan-specific ones into separate commits (`[ROOMSCAN]`-prefixed). Highlights: auth-gated `GET /api/documents` (previously reachable unauthenticated) + closed a tier-3 document visibility leak in `match_chunks` (migration `045`; RAGAs-verified 2026-08-02, no regression — a hand-check of the actual private-document scenario is still open, see STATE.md); real per-user Document Library + staff petition-review UI (previously curl/Postman only); consolidated 5 duplicated voice-input implementations into `frontend/src/hooks/useVoiceInput.js`; fixed the project switcher (was passing a whole object where the backend expects a plain id, so switching silently never worked) and a stale sticky-default bug in the kickoff project-name field; superadmin project visibility (other users' projects render inert with owner identity, not hidden) with the two previously-inconsistent superadmin checks unified into `useIsSuperAdmin`; browser-specific mic-permission-denied instructions (no cross-browser deep link into permission settings exists, so this is the achievable version); kickoff flow gets a free-form text/talk entry path (AI-extracted, pre-fills the existing step wizard for review, never bypasses it). 832 backend + 92 frontend tests passing. Full detail: `journals/session_20260801.md`.
- [x] **Agent Architecture Phase 5 — answer agents + Evaluator + Performance Review + feedback + dashboard v2 + ontology core (2026-07-26)** ([docs/agent_architecture.md](docs/agent_architecture.md)) — the course-cut-line demo tier, all 8 components built and green (**581 pytest**, new files ruff-clean, `npm run build` clean). **Feedback loop + dashboard v2 are deployed to prod** (migration `033` on the real RDS, GHA green, loop verified end-to-end: 👎 → attribution → dashboard confirm). **Citation Verifier #9 and Permit Strategy #11 are wired into the live path** (Manager wave 5 / `GET /projects/{id}/permit-strategy`); **Query Deconstructor #5 is deferred** (a retrieval-fan-out rewrite — validate on the real corpus before wiring). **Feedback loop:** migration `033_answer_feedback`, `POST /query/feedback`, `AnswerResponse.run_id`, QueryPage 👍/👎 + comment. **Performance Review (#24)** (`evaluation/perf_review.py`): attributes a 👎 to an agent from the run trace — deterministic-first (errored step / grounding abstain need no model), else one top-tier call — and writes an *unconfirmed* `agent_corrections` row a human confirms in the dashboard (never silent blame); batch-driven by `scripts/review_feedback.py`. **Evaluator (#23)** (`evaluation/agent_eval.py`): scores each agent against its metric contract (scorecard + correction rate + latest RAGAs faithfulness) and, on a breach, files an action item + auto-demotes one autonomy level; `scripts/run_agent_eval.py`. **Citation Verifier (#9)** (`rag/agents/citation_verifier.py`): deterministic token-span match first, one batched entailment call on the leftovers, missing-chunk citations flagged unsupported. **Query Deconstructor (#5)** (`rag/agents/deconstructor.py`): compound question → sub-questions + per-sub filters, deterministic gate for simple queries. **Permit Strategy (#11)** (`rag/agents/permit_strategy.py`): permit set (mirrors `frontend/src/projectPermitRules.js`) + pull-order sequencing + fee estimate. **Field Ontology core** (`forms/ontology.py`, new `forms/` package): canonical vocabulary + per-field type/validation + source binding (a git-tracked module, no migration). **Dashboard v2 & Agent Glossary** (`api/routes/agents_admin.py` + `frontend/src/admin/`): Scorecard, Agent Glossary (`GET /admin/agents/glossary`), Corrections confirm-queue, and Autonomy control tabs on `/admin/agents`.
- [x] **Agent Architecture Phase 4 — Media Curator (#17), Phase 4 CLOSED** ([docs/media-curator-plan.md](docs/media-curator-plan.md)) — diy how-to help without ever letting video/community text ground a **compliance** answer (segregated `documents.content_class ∈ {authority, how_to}`, enforced in SQL). Shipped on prod (2026-07-25): **B1** curated links (`030_media_refs`, deterministic diy-only `rag/agents/media.py` curator, Guardrail zero-unsourced-URL gate, `AnswerResponse.media_refs`, QueryPage "How-to videos"); **C1** transcripts (`031_media_transcripts`, `content_class` segregation with a non-breaking 3-arg `match_chunks` + new `match_how_to_chunks`, `ingestion/transcript.py`, RAGAs non-regression); **C2** the diy compliance-abstain → grounded how-to answer (`retrieve_how_to`, `Manager._how_to_fallback`, `AnswerResponse.how_to` + amber educational disclaimer); **semantic links** (H2-6.1 — `fetch_media_refs_for_how_to_docs`, so any ingested video surfaces with **no per-video `task_key`**); and **This Old House channel data** (18 videos / 128 chunks) synced to prod via `sync_how_to_to_prod.py` (copies already-embedded how-to data local→prod, no re-fetch, sidesteps YouTube IP blocks). Ops tooling merged to `deployment/sites`: **channel crawl** (`032_media_channels` + `media_refs.channel_id`, RSS enumeration + `@handle`/URL resolver, `crawl_media_channels.py`), **throttle + block-aware ingest** (`TranscriptBlocked` vs no-captions, `--delay` / `--max-blocks` circuit-breaker), and the sync script. Migrations `030`/`031`/`032` applied on prod. **Deferred (NOT Phase 4 blockers), tracked in the plan:** B2 `web_search` (needs `run_agent tools=` + the `claude-api` skill), link liveness → **Freshness Watcher #15**, proxy (`YOUTUBE_PROXY_*`) for at-scale ingest, and a multi-sample live RAGAs baseline → **Evaluator #23**. Slice detail: [B1/B2](docs/plan_media_curator.md), [C1/C2](docs/plan_media_transcripts.md).
- [x] **Agent Architecture Phase 4 core — Prompt Router + versioned fragment library + persona-aware `max_tokens`** ([docs/agent_architecture.md](docs/agent_architecture.md)) — `rag/agents/prompt_router.py` (agent #2) composes the system prompt per request from hand-authored, versioned fragments in `rag/prompts/` (`base ∥ persona ∥ jurisdiction ∥ intent ∥ experience ∥ bounded project notes`) by **lookup, not an LLM call**. Persona playbooks (`diy`/`contractor`/`hiring_contractor`/`research`), 7 jurisdictions, 5 intents, 2 experience modifiers. **`research` is the default — never `diy`** (a confident wrong DIY answer is the costliest default failure). `max_tokens` is now **persona/intent-aware**, killing the hard-coded 1024 that truncated `diy`/`hiring_contractor`; `stop_reason == "max_tokens"` trips the **Guardrail** (`rag/agents/guardrail.py`), which files a deduped action item. Kickoff demoted from a free-text `custom_system_prompt` blob to **bounded, sanitized notes** (≤200 tokens, composed last); migration **029** adds `projects.experience` + `projects.project_notes`. A **Clarification nudge** (`persona_nudge` on the answer) surfaces when no persona was set. **Eval hooks:** every trace + eval run records the exact `prompt_fragment_ids@version` (fragment-attributable quality shifts); `langsmith_eval.run_pipeline` takes a `persona` for comparable per-persona experiments; `evaluation/persona_checks.py` adds deterministic persona-appropriateness checks (the LLM-judge version is Phase 5). Media Curator (#17) is deferred to a second pass. **Verified 2026-07-25:** machine-A **474 pytest** + ruff-clean + `verify_phase2 --no-db` 18/18; machine-B 3-persona demo (029 applied; three genuinely different answers, persona `max_tokens` 2048/640/1792, zero truncation, 100% appropriateness incl. `hiring_contractor` questions+red-flags); fresh **live** RAGAs baseline `ragas_20260725_011651.json` (avg faithfulness 0.843, un-routed path → non-regression confirmed; the 0.007 miss is entirely q6's ±0.15 judge swing, measure-not-gate). **Deployed to prod 2026-07-25** (merged to `deployment/sites`, 029 applied on prod RDS, GHA green, `/api/documents`=19). The follow-on **query-UX pass** (grounding-floor miss → conversational 200 abstain, `persona_nudge` 💡 banner rendered, UI `top_k` 5→8) is **also deployed to prod 2026-07-25** — code + frontend only, no migration; verified live (deployed bundle serves the abstain card + nudge, `/api/documents`=19). Media Curator (#17) is next.
- [x] **Agent Architecture Phase 3 — Corpus Metadata Validator + backfill + superadmin dashboard v1** ([docs/agent_architecture.md](docs/agent_architecture.md)) — `ingestion/metadata_agent.py` (agent #13): deterministic enum/completeness checks first, then one structured `run_agent` call (Sonnet-tier) for content-vs-metadata agreement + `effective_date` extraction, **every proposal carrying a source-chunk citation**. Writes route through `ingestion/governance.py` only (`apply_metadata_correction`, the single corpus writer); the backfill never drafts a live doc (that would empty retrieval — drafting is the ingest path). Supersession detection keys on the real `-YYYYMMDD` re-scrape convention, **not** `-vN` (those are split-PDF parts, not versions). Migration **028** (enum extensions: `verification_stage += 'metadata'`, `verification_result += 'needs_review'`). Superadmin dashboard `/admin/agents` (`api/routes/agents_admin.py` + `frontend/src/admin/`, gated front and back): action queue, metadata review with **inline-editable proposals** (approve → governance + a correction row), and a read-only **Documents** metadata view. `run_agent` also learned to drop the `temperature` param for models that deprecated it (Sonnet 5 / Opus 4.8). **Verified and deployed 2026-07-24**: machine A 442 tests + `verify_phase2 --no-db` 18/18; machine-B validator dry-run 19/19 `needs_review` with cited proposals, zero drops/false-flags; dashboard live on prod. Remaining is operational — apply 028 on prod + backfill `--apply` + approve proposals (STATE punch list).
- [x] **Agent Architecture Phase 2 — Manager + artifact store + Budget Governor** ([docs/agent_architecture.md](docs/agent_architecture.md)) — the hand-wired `/query/answer` chain ported behind `rag/agents/manager.py` with **zero behaviour change**: `tests/test_query_answer_route.py` stays green with no edits to its assertions. Adds `rag/agents/artifacts.py` (`ArtifactRef` — the Manager sees ids + summaries, never chunk text, which is what bounds the ReAct loop) and `rag/agents/budget.py` (deterministic Budget Governor: per-request cap, ladder selection, degradation — shipped **uncapped by default**, so it is a no-op this phase). `rag/generator.py`'s inline Anthropic call folded into `run_agent`, the last remaining call site; `LLM_MODEL` is passed as an explicit override so the ladder does not silently swap prod's pinned model. No new migration. **Verified and deployed to prod 2026-07-24**: machine A (398 tests, `test_query_answer_route` unchanged, `verify_phase2 --no-db` 18/18) + machine B (`verify_phase2 --local` 26/26; generator fold shown behaviour-preserving — pre-Phase-2 code scored the RAGAs q6 query *below* Phase 2, so that floor miss is a corpus/judge signal, not the fold). The RAGAs faithfulness number is **not** a gate here — the judge varies ±0.15 on one query.
- [x] **Agent Architecture Phase 1 — runtime + registry + autonomy enforcement** ([docs/agent_architecture.md](docs/agent_architecture.md)) — `rag/agent_runtime.py` as the single Anthropic call site (native `messages.parse` structured outputs, cheap/mid/top model ladder, measured prompt caching that refuses the silent-no-cache footgun, `count_tokens` budgeting, retries, automatic tracing, and fail-closed autonomy enforcement), plus `rag/agents/registry.py` (`AgentSpec` + lazy binding, rag self-registers, commerce/forms/bids injected by `api/main.py`). `rag/design_intent.py`'s inline Anthropic call folded into the runtime. No new migration. Verify with `py scripts/verify_phase1.py --local`. **Verified and deployed to prod (2026-07-24, `verify_phase1.py` 10/10 against RDS incl. the live caching assertion).**
- [x] **Agent Architecture Phase 0 — trace store + chunk-leakage fix** ([docs/agent_architecture.md](docs/agent_architecture.md)) — migration 026 (`agent_runs`, `agent_steps`, `agent_corrections`, `agent_action_items`, `agent_autonomy`), the three previously-empty `audit/` modules implemented, `@traced`/`@traced_run` wired onto `generate_answer` and `design_intent`, and reranker-rejected chunks no longer prompted or billed
- [x] [On-Demand URL Pull](docs/on_demand_url_pull.md) — `ingestion/url_normalize.py`, `ingestion/page_crawler.py`, migration 022 identity keys + backfill script, `POST /admin/documents/pull-page` + job poll, Pull-from-URL tab on `/upload`. End-to-end verification checklist in the plan doc still pending.
- [x] Sprint 17: Conversational Project Kickoff — Interactive LLM-driven dialog to extract user persona, budget, and materials. Automatically synthesizes a project-specific custom system prompt (migration 020) which is injected into all future compliance queries.
- [x] Sprint 17: Room generative preview — `POST /commerce/room-preview-image`, OpenAI/mock images, device `asset_url`, AR prefers generated asset over product photo ([docs/room_generative_preview.md](docs/room_generative_preview.md))
- [x] Sprint 17: Room design Preview/Save — scan_id design-intent API, token usage (migration 018), `redesign.json` v2 revisions on device, `RoomDesignPage`, DXF export, demoted Scan House
- [x] Sprint 16: Commerce overlays — `commerce/` module, SerpApi HD resolver + mock fallback, `product_ref` / qty takeoff on design intent, product cards + materials estimate UI, AR product textures
- [x] Sprint 15: Scan library UX — profile Room Scans, per-project dashboard (`/projects/:id/dashboard`), link scans from library, migration 017
- [x] Sprint 13: Capacitor Mobile — Capacitor 7 shell, mobile auth, mini-RAG, corpus sync, asset lifecycle scaffolds, room capture plugin stubs, migration 015, mobile CI, prod deploy ECS `:11`, Android Phase 0 (email + RAG)
- [x] Sprint 12: Project Kickoff Wizard — 5-step post-login wizard (`/kickoff`), migration 014 fields (address, spaces, work types, recommended permits), rule-based permit recommendations, kickoff summary on `/projects` detail
- [x] Cognito Auth Migration (Sprint 11) — Replaced custom JWT/Argon2id with Amazon Cognito RS256 JWKS verification, Google SSO, optional TOTP 2FA, lazy RDS user provisioning via `GET /auth/me`
- [x] Get GIS auto-address bar working (Implemented Mapbox Search Box session_token management for address autocomplete suggestions and geocoding retrievals)
- [x] Add mobile styles (SGP10: Responsive styling for mobile, tablet, and desktop viewports, scrollable data tables, and WCAG AAA touch target size conformance)
- [x] [Document Governance UI](docs/sprint11_document_updates.md) — `DocumentAdminPanel.jsx` + `documentAdminUtils.js`: metadata edit + supersede on `/documents` via `X-Admin-Token`. Confirmed shipped via code (2026-07-28 doc health check); live-UI verification checklist in the plan doc still not re-run. _(Not the same "Sprint 11" as the Cognito Auth Migration line above — two different plans reused the sprint number; recorded, not renumbered.)_

---

## Local Development Setup

### Prerequisites

- Python 3.11+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running)
- Node.js 18+ and npm (for the frontend)

---

### Step 1 — Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -e ".[dev]"
pip install sentence-transformers einops   # local embedding model
```

---

### Step 2 — Environment variables

Local dev uses **split env files** — see [docs/environment_setup.md](docs/environment_setup.md).

```powershell
Copy-Item .env.local.example .env.local
Copy-Item .env.example .env
Copy-Item frontend\.env.local.example frontend\.env.local
```

| File | Purpose |
|------|---------|
| `.env.local` | Docker Postgres (`localhost:5433`), CORS, Neo4j — auto-loaded locally |
| `.env` | Secrets only: `ANTHROPIC_API_KEY`, `API_ADMIN_TOKEN`; also `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID`, `COGNITO_REGION` |
| `frontend/.env.local` | `VITE_MAPBOX_TOKEN` for address autocomplete |

Production (AWS/ECS) uses Terraform task env + SSM — no dotenv files in the container.

**Minimum secrets to fill in `.env`:**

| Variable | What to set |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `API_ADMIN_TOKEN` | Random string for `/admin/*` routes |
| `COGNITO_USER_POOL_ID` | e.g. `us-east-1_HF3i1xgNF` (from AWS Cognito) |
| `COGNITO_APP_CLIENT_ID` | e.g. `21admh46opa2gaaii3oaq0nlgd` (from AWS Cognito) |
| `COGNITO_REGION` | e.g. `us-east-1` |
| `SERPAPI_API_KEY` | *(optional)* SerpApi key for live Home Depot product search — see [Commerce / SerpApi](#commerce--serpapi) |
| `OPENAI_API_KEY` | *(optional)* OpenAI key for generative room preview images — mock PNG when unset ([docs/room_generative_preview.md](docs/room_generative_preview.md)) |
| `OPENAI_IMAGE_MODEL` | *(optional)* default `gpt-image-1` |
| `LEONARDO_API_KEY` | *(optional)* Leonardo.ai API key for generative room preview images and textures — fallback to OpenAI then mock when unset |
| `LEONARDO_IMAGE_MODEL` | *(optional)* default `de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3` (Leonardo Phoenix 1.0) |
| `FAL_API_KEY` | *(optional)* fal.ai key for generative room preview images/textures — preferred over Leonardo/OpenAI when set; genuinely tileable PBR material output via PATINA ([docs/room_generative_preview.md](docs/room_generative_preview.md)) |

Database URLs are in `.env.local` (already point at Docker on port 5433).

---

## Commerce / SerpApi

After a room scan, design intent (e.g. *"white subway tile backsplash"*) resolves to **real Home Depot SKUs** with price, stock hints, and a deep link. Implementation: [`commerce/serpapi_client.py`](commerce/serpapi_client.py) + [`commerce/product_resolver.py`](commerce/product_resolver.py).

**What SerpApi does:** Home Depot has no public product API. SerpApi is a paid third-party service that searches `homedepot.com` by keyword + zip and returns structured JSON (title, price, image URL, product link, availability). Our backend calls SerpApi only — **never put the key in `frontend/.env.mobile`**.

| Mode | When | What you get |
|------|------|----------------|
| **Mock catalog** | `SERPAPI_API_KEY` unset | Sample tile/paint products for demos and tests |
| **Live HD data** | `SERPAPI_API_KEY` set in `.env` (local) or ECS/SSM (prod) | Real localized search results near project zip |

**Blocker for production pricing:** Until you sign up at [serpapi.com](https://serpapi.com/) and add `SERPAPI_API_KEY` to prod ECS, the app shows **mock products** only. Permit queries and room scans still work; commerce cards use placeholder SKUs.

**Local optional setup:**

```bash
# In .env (repo root) — not in frontend mobile env
SERPAPI_API_KEY=your_serpapi_key
```

**Also required for full mobile commerce flow:** deploy backend with `/api/commerce/*` routes and migration 017 (`user_room_scans`, `project_room_scan_links`). If `run_migration.py` fails with `user_room_scans already exists`, migration 017 is already applied — skip it.

---

### Step 3 — Start the database

```powershell
docker compose up -d
```

This starts a local Postgres 17 + pgvector + PostGIS container on **port 5433**. The schema
(`db/schema.sql`) and init SQL (`db/init/*.sql`) are applied automatically on
first boot.

Verify it is running:

```powershell
docker ps   # should show permit_rag_db as Up
```

> **If the volume already exists** and you want to apply migrations you don't
> have yet, use the migration runner (prints the target DB and refuses a
> remote host without confirmation — see `STATE.md` "Migration drift"):
> ```powershell
> py scripts/apply_migration.py db/migrations/<file>.sql
> ```
> Apply them in ascending numeric order (`db/migrations/` is the source of
> truth for what's current — there is no `schema_migrations` table, so
> `scripts/check_migrations.py --local` is how you check what's already
> applied before running anything).

---

### Step 4 — (First time only) Ingest documents

Skip this if the DB already has data (`chunks` table is populated).

```powershell
# Download source documents
py -m ingestion.harvester harvest

# Chunk + insert into DB
py -m scripts.ingest_documents

# Embed all chunks locally (takes a few minutes — runs nomic-embed-text-v1.5)
py -m ingestion.embedder
```

---

### Step 5 — Start the API

```powershell
py -m uvicorn api.main:app --reload --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

---

### Step 6 — Start the frontend

Open a **second terminal** (keep the API running in the first):

```powershell
cd frontend
npm install       # first time only
npm run dev
```

Open the URL Vite prints — usually `http://localhost:5173`.

Current frontend routes:
- `/` — query flow with answer, citations, source chunk viewer, and debug logs
- `/documents` — document browser with filters and status summary
- `/upload` — admin upload flow with readiness checks and error guidance

---

### Everyday startup (after first-time setup)

To start the entire application stack (Docker databases, FastAPI backend, and Vite frontend) with a single command on Windows, run the orchestrator script from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1
```

To stop all services and shut down database containers:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/stop.ps1
```

*Alternatively, you can start individual services manually:*

```powershell
# Terminal 1 — DB (if not already running)
docker compose up -d

# Terminal 2 — API
py -m uvicorn api.main:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend
npm run dev
```

## AWS Production Deployment

The application is configured for a robust, production-grade cloud deployment on AWS utilizing infrastructure-as-code (Terraform) and automated containerized pipelines.

### Cloud Architecture Overview
*   **VPC & Networking**: Custom VPC with public subnets (hosting the ALB and S3/CloudFront entry points) and private subnets (hosting ECS Fargate container tasks).
*   **Database Tier**: Amazon RDS PostgreSQL instance running in public subnets (to facilitate direct bootstrapping/seeding) with `pgvector` and `postgis` spatial extensions enabled.
*   **API Tier**: ECS Fargate container cluster running FastAPI backend tasks behind an Application Load Balancer (ALB).
*   **Frontend Tier**: Static React SPA hosted in an Amazon S3 bucket and distributed globally via a CloudFront CDN.
*   **Security & SSL**: Traffic is fully encrypted via an ACM Wildcard SSL Certificate (`*.scottsalhanick.com`) bound to CloudFront. Runtime secrets are stored securely in AWS SSM Parameter Store as `SecureString` parameters.

---

### Deployment Prerequisites
1.  **AWS CLI**: Configured locally with administrative credentials (`aws configure`).
2.  **Docker Desktop**: Running locally to compile and build the production backend Docker container.
3.  **Terraform**: CLI installed locally (v1.5+).
4.  **SSM Parameters**: Ensure the following parameters are populated in the AWS Systems Manager Parameter Store as `SecureString` types:
    *   `/permit_rag/prod/anthropic_api_key` (Claude API key)
    *   `/permit_rag/prod/admin_token` (Secure administrative access token)
    *   `/permit_rag/prod/neo4j_bolt_url` (AuraDB graph layer connection URI)
    *   `/permit_rag/prod/neo4j_auth` (Graph credentials, formatted as `neo4j/<your-auradb-password>`)

---

### Initial Setup & Re-provisioning

If you are deploying the AWS infrastructure from scratch:
```powershell
# Deploy all AWS resources
npm run deploy:infra
```

#### Database Initialization
Once Amazon RDS is provisioned, bootstrap the schema tables, custom roles, migrations, and seeds:
1. Retrieve the master database password:
   ```powershell
   terraform -chdir=terraform output -raw db_password
   ```
2. Update the `DATABASE_URL` in your local `.env` to point to the RDS endpoint.
3. Run the bootstrap script:
   ```powershell
   py scripts/init_rds_db.py
   ```
   *(Note: This script automatically drops and recreates the `public` schema on run to guarantee a clean, duplicate-error-free initialization).*

---

### Deploying Updates

Automated root-level NPM commands orchestrate building, packaging, and shipping code changes to AWS:

*   **Deploy Entire Stack**: Runs full infrastructure checks, builds and pushes the backend container to ECR (with ECS rolling restart), and compiles/syncs the frontend to S3 with CDN cache invalidation:
    ```powershell
    npm run deploy
    ```
*   **Deploy Backend Only**: Recompiles the FastAPI backend Docker image (which pre-caches the embedding model inside the container for faster start times), pushes to ECR, and triggers a rolling service update on ECS Fargate:
    ```powershell
    npm run deploy:backend
    ```
*   **Deploy Frontend Only**: Compiles the React static assets, syncs files to the S3 bucket with `--delete` to remove stale assets, and invalidates the CloudFront CDN cache:
    ```powershell
    npm run deploy:frontend
    ```

---

### Production Security & DDoS Protection (WAF & Database Routing)

#### 1. AWS WAF (Web Application Firewall) Setup
To protect your FastAPI backend from API spam and prevent runaway LLM costs (via Claude API calls on the `/query/answer` endpoint), configure a Web ACL with rate-limiting:
1. Go to the **AWS WAF & Shield** console.
2. **Important**: Change your AWS Console region filter to **Global (CloudFront)**.
3. Click **Create Web ACL** and associate it with your CloudFront distribution.
4. Add a custom **Rate-based rule**:
   *   **Rule Type**: Rate-based rule.
   *   **Rate Limit**: `300` requests per rolling 5-minute window per IP.
   *   **Action**: **Block** (returns an HTTP 403 Forbidden page to abusers).
5. Complete the setup and deploy the Web ACL.

#### 2. RDS Database Port Hardening
For initial local migrations, the database was temporarily open to public traffic. Now that bootstrapping is complete, **close the public PostgreSQL port**:
1. Remove the temporary `0.0.0.0/0` ingress block from the RDS security group in `terraform/main.tf`.
2. Apply the firewall changes:
   ```powershell
   cd terraform
   terraform apply
   ```
   *(Your backend ECS containers connect to the RDS database using VPC-internal routing rules, so they do not require public port ingress to function).*

---

## LangChain MCP Adapters (Optional)

`langchain-mcp-adapters` is an optional integration layer that lets LangChain
agents call tools exposed by MCP (Model Context Protocol) servers. In this
project, it is intended for future tool-based workflows and is not required
for core ingestion/retrieval/generation paths.

### Why use it

- Connect LangChain flows to MCP tool servers without custom transport code
- Reuse MCP tool definitions in local or remote agent workflows
- Keep MCP integrations isolated from core app dependencies

### Install / activate

If `langchain-mcp-adapters` is configured as an optional dependency group
(e.g., `mcp`) in `pyproject.toml`:

```bash
# from project root, with venv active
pip install -e ".[mcp]"
```

---

## Project Structure

```
permit_rag/
├── ingestion/          # Document harvesting, chunking, verification
│   ├── harvester.py    # Download + tag municipal documents
│   ├── chunker.py      # PDF/HTML/DOCX/PPTX/TXT extraction + text splitting
│   ├── verification.py # Stage-by-stage ingestion verification
│   ├── embedder.py     # nomic-embed-text-v1.5 local embedding (768-dim)
│   ├── governance.py   # Document lifecycle management
│   ├── url_normalize.py # Shared URL/filename identity normalization
│   └── page_crawler.py # On-demand page link discovery + SSRF guards
├── db/
│   ├── schema.sql      # Base schema (documents, chunks, jurisdictions,
│   │                   #   query_log, municipal_boundaries, + governance/
│   │                   #   audit tables); db/migrations/ layers ~20 more
│   │                   #   (agents, projects, media, feedback, etc.)
│   └── client.py       # psycopg3 connection pool + CRUD helpers
├── rag/                # Retrieval + generation pipeline (active)
├── api/                # FastAPI endpoints (query + documents + admin + health)
├── docs/               # Supplemental docs (API usage examples)
├── evaluation/         # RAGAs evaluation workflows (active)
├── audit/              # Query audit logging (scaffold)
├── frontend/           # Vite + React UI (query + documents + upload)
├── documents/
│   ├── raw/            # Downloaded PDFs + HTML (gitignored)
│   ├── metadata/       # JSON sidecar per document
│   ├── catalog.json    # Source catalog entries for harvester
│   └── registry.json   # Master document registry
├── scripts/            # One-off utilities
├── tests/              # pytest test suite
├── journals/           # Session logs
├── docker-compose.yml  # Postgres + pgvector (pg17)
├── pyproject.toml      # Dependencies + tool config
└── STATE.md            # Current project state
```

---

## Docs Table of Contents

Project docs in `docs/`. ⚠ = flagged in the 2026-07-28 doc health check as
stale/superseded/needing a status pass — not yet resolved.

**Architecture & reference**
| File | Purpose |
|---|---|
| `docs/agent_architecture.md` | Agent roster, phases, cost model, autonomy levels — the design doc |
| `docs/api.md` | API endpoint usage, auth headers, runtime config notes |
| `docs/cognito_groups_rbac.md` | Cognito groups as RBAC source of truth (member/admin/superadmin) |

**LangSmith / observability**
| File | Purpose |
|---|---|
| `docs/langsmith_session_tracing.md` | Enabling tracing, request→trace flow, session grouping |
| `docs/langsmith_prompt_evaluation.md` | Prompt-version tagging + the offline eval harness |
| `docs/langsmith_quickref.md` | One-screen cheat sheet for both of the above |

**Ops, deploy & secrets**
| File | Purpose |
|---|---|
| `docs/aws_deployment_steps.md` | AWS deployment procedure |
| `docs/aws_usage.md` | AWS resource usage notes |
| `docs/env_secrets_strategy.md` | Plan for hardcoded config → GitHub vars/secrets → SSM |
| `docs/environment_setup.md` | Split env file setup (`.env` vs `.env.local`) |
| `docs/github_oidc_setup.md` | GitHub OIDC → AWS setup for CI |
| `docs/offboarding_runbook.md` | User offboarding purge procedure (single + bulk) + verification |
| `docs/secrets_leak_protocol.md` | What to do if a secret leaks |

**Media Curator (Phase 4, shipped)**
| File | Purpose |
|---|---|
| `docs/media-curator-plan.md` | Canonical overview / north star |
| `docs/plan_media_curator.md` | B1/B2 implementation detail (curated links, `web_search`) |
| `docs/plan_media_transcripts.md` | C1/C2 implementation detail (transcripts, how-to answers) |

**Ingestion & room preview**
| File | Purpose |
|---|---|
| `docs/on_demand_url_pull.md` | Admin pull-from-URL: page crawl, checksum diff, ingest |
| `docs/room_generative_preview.md` | Room preview image generation (OpenAI/Leonardo/mock) |

**Mobile**
| File | Purpose |
|---|---|
| `docs/mobile_phase0_gates.md` | Mobile Phase 0 gate checklist (M0-1…M0-9) |
| `docs/mobile_internal_beta_checklist.md` | TestFlight / Play internal beta checklist |
| `docs/mobile_public_store_checklist.md` | Public app store launch checklist |
| `docs/sprint_13capacitor-implementation-overview.md` | How Capacitor wraps the React app |
| `docs/sprint_14_3d-room-capture-agnostic-guide.md` | Platform-agnostic 3D room capture design guide |

**Sprint history & checklists**
| File | Purpose |
|---|---|
| `docs/sprint4_qa_checklist.md` | Sprint 4 QA sign-off (closed) |
| `docs/sprint9_users_projects.md` | ⚠ Sprint 9 auth/projects plan — predates Cognito migration |
| `docs/sprint11_document_updates.md` | Doc governance UI plan — shipped, live-UI checklist not re-run |
| `docs/sprint12_p0_prod_checklist.md` | Sprint 12 web prod checklist |
| `docs/sprint12_user_profile_dashboard.md` | Profile dashboard plan — all 3 phases shipped |
| `docs/task14ab_execution_checklist.md` | PostGIS + first boundary layer execution checklist (closed) |
| `docs/postgis_migration_checklist.md` | PostGIS rollout planning checklist (closed) |
| `docs/ux_audit_260703.md` | Production UX audit — all 4 P0s confirmed fixed; a few P1/P2 still open, see status note in the file |

**Backlog**
| File | Purpose |
|---|---|
| `docs/backlog.md` | Deferred items (GIS expansion, hybrid eval) — old but re-confirmed still current |

---

## Commands

```bash
# Start local Postgres + pgvector (port 5433)
docker compose up -d

# Download all catalog documents
# If a matching doc_id file already exists in documents/raw and --force is not set,
# harvester reuses the local raw file instead of downloading from URL.
py -m ingestion.harvester harvest

# Force re-download even if unchanged
py -m ingestion.harvester harvest --force

# Check all sources for changes (run weekly)
py -m ingestion.harvester monitor

# Print governance summary
py -m ingestion.harvester report

# Edit source entries for harvesting
# (add/remove docs and metadata here)
# documents/catalog.json

# Ingest all passing documents into DB (chunk + insert)
py -m scripts.ingest_documents

# Re-ingest existing doc_ids too (use after normalization changes)
py -m scripts.ingest_documents --include-existing

# Embed a single document (smoke test)
py -m ingestion.embedder texas-contractor-licensing-electrical

# Embed all documents
py -m ingestion.embedder

# Force re-embed all chunks (including already-embedded chunks)
py -m ingestion.embedder --force

# Re-chunk + force re-embed + RAGAs gate, in one script (see "Corpus
# Reprocessing" below for why this needs to be all three, in this order)
scripts/reprocess_corpus.sh --local

# Chunk + verify all documents (no DB insert)
py -m scripts.run_chunk_verify

# Create an API Token
py -c "import secrets; print(secrets.token_urlsafe(32))"

# Purge one uploaded project document (requires admin token/role)
py -m scripts.purge_project_uploads --doc-id "<doc_id>" --admin-role owner

# Purge many docs listed in a text file (one doc_id per line)
py -m scripts.purge_project_uploads --doc-id-file "docs_to_purge.txt" --admin-role owner
```

---

## Corpus Reprocessing

A chunking-strategy change in `ingestion/chunker.py` (a new context prefix, a
new splitting rule, etc.) only affects documents chunked **after** the change
ships — the existing corpus keeps whatever chunks and embeddings it already
had. To measure a change's real effect, or just bring the whole corpus up to
date, re-chunk and re-embed everything and re-run the RAGAs gate:

```powershell
# PowerShell (Windows)
.\scripts\reprocess_corpus.ps1 -Local
.\scripts\reprocess_corpus.ps1 -DatabaseUrl "postgresql://..."

# Bash (Linux / Git Bash)
scripts/reprocess_corpus.sh --local
scripts/reprocess_corpus.sh --database-url='postgresql://...'
```

Runs three steps in order, stopping before the next one if any step fails:

1. **Re-chunk** (`py -m scripts.ingest_documents --include-existing`) —
   re-runs the chunker against every existing document.
2. **Force re-embed** (`py -m ingestion.embedder --force`) — re-chunking
   alone updates a chunk's stored text via upsert but never its embedding
   vector; this step is what actually makes the new content searchable.
3. **RAGAs eval** (`py -m evaluation.ragas_eval --no-answer-cache --export`)
   — the quality gate. Running this before both steps above finish would
   just re-score the old corpus and report "no change" — not because
   nothing improved, but because nothing was reprocessed yet.

A DB target flag (`--local` or `--database-url=...`) is required; there's no
default, and every step prints its own target banner (`scripts/_db_target.py`)
— read it before trusting the run, especially against production. A report
and full log land in `evaluation/results/reprocess_<timestamp>_report.txt`
(and `.log`) regardless of whether the run succeeded or failed partway
through, so a failed run still tells you exactly how far it got.

Not on a schedule yet — run it manually. (A cron job to run this
automatically is a natural next step, not built yet.)

---

## API Quick Start

```bash
# Run API locally
py -m uvicorn api.main:app --reload --port 8000
```

Interactive docs:
- `http://localhost:8000/docs`
- `http://localhost:8000/redoc`

Documented endpoint examples also live in `docs/api.md`.

### API examples

```bash
# Health check
curl -s http://localhost:8000/health

# Retrieval query
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"What are the setback requirements for a residential fence in Dallas?\",\"top_k\":5,\"municipality\":\"dallas\"}"

# List/filter documents
curl -s "http://localhost:8000/documents?municipality=dallas&status=active&authority=municipal&doc_type=building_code"

# Document detail
curl -s http://localhost:8000/documents/dallas-building-code

# Status aggregation for current filter scope
curl -s "http://localhost:8000/documents/status?municipality=dallas&authority=municipal"

# Admin metadata patch (set API_ADMIN_TOKEN in env to enforce header auth)
curl -s -X PATCH http://localhost:8000/admin/documents/dallas-building-code \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: admin" \
  -d "{\"document_status\":\"draft\",\"retrieval_weight\":0.55}"

# Admin supersession action
curl -s -X POST http://localhost:8000/admin/documents/dallas-building-code-2024/supersede \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: admin" \
  -d "{\"replacement_doc_id\":\"dallas-building-code-2026\",\"superseded_weight\":0.1}"

# Admin purge action (deletes chunks/vectors + local raw file, keeps repealed tombstone row)
curl -s -X POST http://localhost:8000/admin/documents/project-doc-1/purge-project-upload \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: owner"

# On-demand URL pull (discovers linked files on the page, ingests only changes)
curl -s -X POST http://localhost:8000/admin/documents/pull-page \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: admin" \
  -d "{\"url\":\"https://city.gov/building/forms\",\"municipality\":\"dallas\",\"authority_level\":\"municipal\",\"doc_type\":\"permit_checklist\",\"subject_tags\":[\"permits\"]}"

# Poll pull job progress + per-file verdicts (new/updated/skipped/flagged/failed)
curl -s http://localhost:8000/admin/documents/pull-jobs/<job_id> \
  -H "X-Admin-Token: ${API_ADMIN_TOKEN}" \
  -H "X-Admin-Role: admin"
```

Admin runtime security/env flags:
- `API_ADMIN_AUTH_REQUIRED=true|false` (default `true`)
- `API_ADMIN_TOKEN=<secret>`
- `API_ADMIN_ALLOWED_ROLES=admin,owner` (default `admin`)
- `API_PURGE_ANY_TIER_ROLES=owner` (roles allowed to purge non-project tiers)
- Admin token policy: rotate `API_ADMIN_TOKEN` every 30 days and on any suspected secret exposure or admin roster change.

CORS/env flags:
- `API_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:5173`
- `API_CORS_ALLOW_ALL=true` (dev-only wildcard override)

API errors (including validation) are normalized as:
- `{"detail": "<string>"}`

---

## Document Ingestion Pipeline

Use this workflow for deterministic ingestion with normalization and embedding refresh.

### 1) Set normalization + retrieval controls in `.env`

```bash
CHUNK_NORMALIZATION_ENABLED=true
CHUNK_PROCEDURAL_FILTER_ENABLED=true
CHUNK_PROCEDURAL_DROP_THRESHOLD=3
CHUNK_FILTER_WARN_DROP_RATIO=0.50
RETRIEVAL_PROCEDURAL_PENALTY_ENABLED=true
RETRIEVAL_PROCEDURAL_PENALTY=0.015
RETRIEVAL_PROCEDURAL_MAX_HITS=4
RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED=true
RETRIEVAL_NON_MUNI_MUNICIPAL_PENALTY=0.06
RETRIEVAL_NON_MUNI_SCOPE_MATCH_BONUS=0.02
RETRIEVAL_NON_MUNI_SCOPE_MISMATCH_PENALTY=0.03
# Hybrid retrieval rollout (default off for safe fallback)
RETRIEVAL_HYBRID_ENABLED=false
RETRIEVAL_DENSE_TOP_N=20
RETRIEVAL_BM25_TOP_N=20
RETRIEVAL_RRF_K=60
RETRIEVAL_RRF_DENSE_WEIGHT=1.0
RETRIEVAL_RRF_BM25_WEIGHT=1.0
```

### 2) Download/update sources

```bash
# Reuse local raw files when doc_id files already exist
py -m ingestion.harvester harvest
```

### 3) Ingest to DB

```bash
# New docs only (default)
py -m scripts.ingest_documents

# Include existing docs (recommended after cleaning/normalization changes)
py -m scripts.ingest_documents --include-existing
```

### 4) Embed vectors

```bash
# Standard embed (only chunks with NULL embeddings)
py -m ingestion.embedder

# Force re-embed all chunks (use after major text normalization updates)
py -m ingestion.embedder --force
```

### 5) Validate ingestion quality

```bash
# Retrieval previews for weak queries
py -m rag.pipeline --municipality dallas --top-k 10 "What are the setback requirements for a residential fence in Dallas?"
py -m rag.pipeline --top-k 10 "What are the ADA accessibility requirements for commercial buildings?"
py -m rag.pipeline --municipality plano --top-k 10 "What are the building permit requirements in Plano?"
py -m rag.pipeline --municipality dallas --top-k 10 "What are the fire sprinkler requirements for new construction in Dallas?"

# Production RDS preflight (run before RAGAs against prod corpus from laptop)
$env:ENVIRONMENT="production"; py -m evaluation.prod_preflight

# Production RAGAs faithfulness eval (uses DATABASE_URL from .env.production + secrets from .env)
# NOTE: use --no-answer-cache, NOT $env:RAGAS_ANSWER_CACHE_ENABLED="false". bootstrap_env()
# runs inside the process and calls load_dotenv(override=True), so the env var is overwritten
# by the dotenv files (.env.local.example ships it as `true`). A cached run never calls
# generate_answer, so it scores stale answer text and reports 0ms generation latency while
# looking healthy -- it silently measures nothing. eval_guard now hard-fails such a run.
$env:ENVIRONMENT="production"; $env:LLM_PROVIDER="anthropic"; $env:LLM_MODEL="claude-haiku-4-5-20251001"; $env:RETRIEVAL_HYBRID_ENABLED="false"; py -m evaluation.ragas_eval --export --no-answer-cache

# Focused RAGAs pass then full suite (local Docker Postgres)
py -m evaluation.ragas_eval --query 0 1 2 3 5 --export --no-answer-cache
py -m evaluation.ragas_eval --export --no-answer-cache

# Regression guard against confirmatory baseline (fails on metric drift)
py -m evaluation.eval_guard --candidate evaluation/results/ragas_20260601_010352.json

# Hybrid retrieval validation (feature-flagged)
$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m rag.pipeline --municipality dallas --top-k 10 "What are the setback requirements for a residential fence in Dallas?"
$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m rag.pipeline --municipality dallas --top-k 10 "What are the fire sprinkler requirements for new construction in Dallas?"
$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m evaluation.ragas_eval --query 0 1 2 3 5 --export --no-answer-cache
$env:RETRIEVAL_HYBRID_ENABLED="true"; py -m evaluation.ragas_eval --export --no-answer-cache
```

Notes:
- `chunk_document()` logs normalization stats (`chunks_before_filter`, `chunks_dropped`, `chunk_drop_ratio`).
- If `chunk_drop_ratio` exceeds `CHUNK_FILTER_WARN_DROP_RATIO`, review source quality and thresholds.
- Hybrid mode is rollback-safe: set `RETRIEVAL_HYBRID_ENABLED=false` to return to dense-only retrieval immediately.
- As of 2026-05-31 latest full run (`ragas_20260531_102544.json`), hybrid faithfulness is `0.852` (gate pass), but q1 remains unstable; keep `RETRIEVAL_HYBRID_ENABLED=false` by default until one more confirmatory full run.
- `evaluation.eval_guard` defaults to baseline `evaluation/results/ragas_20260531_122639.json` and fails if avg faithfulness drops below `0.85` or q1 faithfulness drops by more than `0.10`. It also hard-fails a candidate whose rows are all `answer_cache_hit` (a run that never called `generate_answer` measures nothing). **Caveat:** the default baseline is a cached-era run and single-shot RAGAs swings ±0.15 on one query — always compare against a fresh **live** run (`--no-answer-cache`) and treat one number as a signal, not a gate. Re-establishing a clean live baseline is Phase 3 debt (STATE punch list).
- `evaluation.prod_preflight` loads `.env.production` when `ENVIRONMENT=production`, verifies the URL is prod RDS (not localhost), prints document/chunk counts, exits `1` if the corpus is empty. Run it before prod RAGAs eval; it does not call the live HTTPS site — it reads the same RDS corpus the API uses.
- Keep `STATE.md` as a compact current snapshot; store dated metric timelines and per-run deltas in `journals/` session logs.

RAGAs metric definitions used in this repo:
- **Faithfulness**: How well the answer is supported by retrieved context (higher = less hallucination).
- **Relevancy**: How directly the answer addresses the user query.
- **Context precision**: How much of the retrieved context is actually useful/relevant to the query.
- **Top similarity (`top_sim`)**: Similarity score of the highest-ranked retrieved chunk for that query.

### LangSmith Tracing & Prompt Version Tracking

Additive to RAGAs, not a replacement — `evaluation/langsmith_eval.py` reuses the same
guardrail/generation pipeline but uploads to LangSmith for dataset versioning and
experiment-comparison in the UI, and `api/routes/query.py` sends live `/query/answer`
traffic there as traces when enabled.

```bash
# Enable tracing (.env)
LANGSMITH_API_KEY=...
LANGCHAIN_TRACING_V2=true

# Run the LangSmith eval harness (uploads an experiment run)
py -m evaluation.langsmith_eval                          # default dataset: permit_rag_eval_v1
py -m evaluation.langsmith_eval --dataset permit_rag_security_v1
py -m evaluation.langsmith_eval --experiment-prefix manual-smoke
```

**System prompt changes are not tracked by a LangSmith-managed prompt (no Prompt Hub
integration yet)** — `SYSTEM_PROMPT` in `rag/generator.py` is a plain Python string,
same as any other code change, so `git log -p rag/generator.py` is still the diff/changelog.
What LangSmith gives you instead is correlation: `rag.generator.PROMPT_VERSION` is
attached as `prompt_version` metadata on both the `/query/answer` trace (root + generation
spans) and on `langsmith_eval` experiment runs. Bump `PROMPT_VERSION` every time you edit
`SYSTEM_PROMPT`, then in the LangSmith UI filter/group runs by the `prompt_version`
metadata field to see how faithfulness, latency, or token counts shifted around that edit.

---

## Ingestion Health Check

Use this quick checklist after catalog or harvesting changes:

```bash
# Validate catalog loader and duplicate/required-field checks
py -m pytest tests/test_harvester_catalog.py

# Rebuild registry from current catalog/raw state
py -m ingestion.harvester harvest

# Compare catalog vs registry coverage and list missing doc_ids
py -m ingestion.harvester report

# Ingest to DB and refresh vectors
py -m scripts.ingest_documents --include-existing
py -m ingestion.embedder --force
```

Expected health indicators:
- Harvester summary prints `Used local raw` and `Downloaded from URL` counts.
- `report` shows `Catalog documents`, `Registry documents`, and `Missing from registry`.
- Missing list should only contain intentionally non-harvestable/manual-only sources.

---

## Chunking Strategy

Documents are split using **recursive character splitting**
([LangChain RecursiveCharacterTextSplitter](https://python.langchain.com/docs/modules/data_connection/document_transformers/recursive_text_splitter/)),
tuned for legal/code text.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Chunk size | 1,500 chars | ~375 tokens for nomic-embed-text-v1.5 (8K context). Holds a complete code section. |
| Overlap | 200 chars | Prevents splitting mid-sentence at boundaries. |
| Split hierarchy | Section → paragraph → line → sentence → clause → word | Prefers clean breaks between legal sections. |

### Split hierarchy (tried in order)

1. `\n\n\n` — section breaks
2. `\n\n` — paragraph breaks
3. `\n` — line breaks
4. `. ` — sentence ends
5. `; ` — clause breaks
6. `, ` — comma breaks
7. ` ` — word breaks

### Optimization plan

Chunk size and overlap will be empirically tuned in Week 4–5 via
ablation study using [RAGAs](https://docs.ragas.io/) metrics:

- Grid search: chunk_size ∈ {500, 1000, 1500, 2000, 3000},
  overlap ∈ {0, 100, 200, 400}, top_k ∈ {3, 5, 10}
- Metrics: context precision, context recall, faithfulness,
  answer relevancy
- Evaluation set: ~30–50 hand-written questions with known
  ground-truth answers from ingested documents

### Pipeline

```
Raw file (PDF/HTML)
  → Text extraction (pypdf / BeautifulSoup)
  → Clean text (normalize whitespace, strip boilerplate)
  → Recursive split (1500 chars, 200 overlap)
  → Verification (coverage ≥ 80%, ≥ 1 chunk)
  → Chunks ready for embedding
```

---

## Metadata Schema

Every document in the registry carries full governance metadata:

```json
{
  "doc_id": "city-of-dallas-ordiance-v1",
  "source_url": "https://codelibrary.amlegal.com/...",
  "municipality": "dallas",
  "authority_level": "municipal",
  "doc_type": "zoning_ordinance",
  "subject_tags": ["zoning", "land-use", "setbacks"],
  "document_status": "active",
  "is_current": true,
  "retrieval_weight": 1.0,
  "review_due": "2026-07-21",
  "checksum_sha256": "a3f9...",
  "ingested_at": "2026-05-22T22:16:04Z"
}
```

---

## Document Governance

- Documents are **never deleted** — only superseded or repealed
- Superseded docs get `retrieval_weight: 0.1` (deprioritized, not removed)
- Scanned PDFs are flagged as `needs_ocr`, not silently ingested
- Verification runs at every ingestion stage — no silent failures
- Source URL changes are flagged for human review

```python
from ingestion.harvester import mark_superseded

mark_superseded(
    old_doc_id="dallas-zoning-ord-2022-11",
    new_doc_id="dallas-zoning-ord-2024-03"
)
```

---

## Architecture Decisions

- **Local Postgres 17 + pgvector** for dev; Supabase or RDS for production
- **psycopg3** (direct driver) over Supabase SDK — no vendor lock-in
- **Docker Compose** for local Postgres (pgvector/pgvector:pg17 image, port 5433)
- **FastAPI** over Flask (async support, auto OpenAPI docs)
- **Vite + React** over Next.js (simpler for MVP)
- **Claude API** for generation; **nomic-embed-text-v1.5** for embeddings (768-dim, local inference)
- **Hybrid search implemented (feature flag)**: dense (pgvector HNSW) + BM25 (tsvector + GIN) with RRF fusion, defaulted off pending faithfulness/regression gate
- **Citations** must reference publisher + date, never imply direct city authority
