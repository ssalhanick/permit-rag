# Session 2026-07-25 — deploy reconcile + Media Curator (#17) Slice B1

Branch: started on `agents/phase-4`; B1 code belongs on `feat/media-curator` (see
git note). Machine A (repo machine, macOS; `.venv` has deps; empty DB, no corpus).

## Task (restated at session start)

Pre-session prompt: **deploy the query-UX pass**, then **build Media Curator #17**.
On inspection the deploy was already done (below), so the session became:
1. reconcile the deploy state, and
2. build **Media Curator Slice B1** (owner chose "plan first", approved the plan +
   the `030` migration number, said "start Slice B1").

## Part 1 — the query-UX deploy was already live

Documented as "pending deploy," but git disagreed: `deployment/sites` (local **and**
fetched `origin`) = `45f4c13` (the query-UX commit); reflog `@{0}` = a fast-forward
merge of `agents/phase-4`. `deploy.yml` fires on push to `deployment/sites`, and
`45f4c13` touches `api/`+`rag/`+`frontend/`, so both jobs ran at the end of the
prior working block. Verified live this session:
- `frontend/ npm run build` → clean (only the pre-existing >500 kB chunk warning).
- Served prod bundle (`assets/index-BfhgwmxH.js`) contains `No confident answer
  found`, `persona_nudge`, `top_k:8`.
- `/api/documents` = 19.

Not machine-checkable here: the interactive click-through behind Cognito login —
left for the owner. Docs reconciled (README, STATE, the phase-4 journal). Committed
as `b93f3a7` (a stray trailing `"` in the handed-off one-liner aborted the compound
command after the commit, so `b93f3a7` is on `agents/phase-4` only — the
ff-merge-to-`deployment/sites` + push still needs running; folded into the B1 git
flow below).

## Part 2 — Media Curator Slice B1 (BUILT, machine-A verified offline)

**Key finding that shaped the design:** `rag/agent_runtime.run_agent` has **no
`tools=` parameter** (`agent_runtime.py:409-426` — only `messages.parse`/`create`).
So the `web_search` path needs a runtime extension, while the curated-table path
needs none. → staged B1 (deterministic table) / B2 (web_search). Plan written to
`docs/plan_media_curator.md`; README Planned entry re-pointed at it.

Built (all deterministic, no LLM, $0):
- **`db/migrations/030_media_refs.sql`** — `CREATE TABLE IF NOT EXISTS media_refs`
  (task_key, title, url, provider, jurisdiction, relevance_note, last_verified_at,
  active) + partial index; `text + CHECK` (provider youtube, url https),
  `UNIQUE (task_key, url)` for idempotent seeding. Additive/idempotent. Takes the
  `030` slot; Phase-6 ontology cascades to `031`. **Not in `schema.sql`** (that's
  the Week-1 base; 026/029 tables aren't in it either).
- **`db/client.py`** — `fetch_media_refs(task_key, jurisdiction, limit)`
  (jurisdiction-match-before-national, most-recently-verified first) +
  `insert_media_ref(...)` (seed-only writer, `ON CONFLICT DO NOTHING`).
- **`rag/agents/media.py`** (agent #17) — `curate(query, *, persona, jurisdiction,
  permit_types)`. Diy-only (else `[]`); `_derive_task_key` keyword map (first-match;
  a Crystallizer target); returns `MediaRef(sourced=True)`; never fabricates a URL;
  lookup failure degrades to `[]`. Registered in the roster (`__init__.py`, now 13).
- **`rag/agents/guardrail.py`** — `check_media_sources(items)` drops any URL not on
  youtube.com (domain/subdomain) and not carrying `sourced=True`; files a deduped
  `unsourced_media_url` action item on a drop; never raises. The zero-unsourced-URL
  hard gate — inert on the B1 DB path, live once B2 can emit model URLs.
- **`rag/agents/manager.py`** — `_route_prompt` persists `state.resolved_persona`;
  new `_curate_media` step added to wave 4 (`(_generate, _curate_media)`), diy-only,
  skip on abstain, results through the Guardrail gate; `media_refs` threaded through
  `_PlanState` + `ManagerResult` + `_assemble`. Best-effort (never fatal).
- **`api/schemas.py`** — `MediaRefResponse` + `AnswerResponse.media_refs` (default
  `[]`). **`api/routes/query.py`** — `_media_ref_responses(plan)` maps onto the
  success-path response (abstain path stays empty by default).
- **`frontend/src/QueryPage.jsx`** — "📺 How-to videos" section, rendered only when
  `media_refs` is non-empty; links open in a new tab.
- **`scripts/seed_media_refs.py`** (target-safe via `_db_target`, dry-run default,
  `--apply`, `--verified`) + **`scripts/media_refs_seed.json`** (3 PLACEHOLDER
  entries — the owner replaces URLs with vetted links before `--apply --verified`;
  links must be human-checked, which is the governance point).
- **Tests:** `tests/test_media_curator.py` (diy→videos, non-diy→none, no-task→none,
  derivation, lookup-failure→none); `test_guardrail.py` (+6 media-gate cases:
  keep youtube/subdomains, drop unsourced + file item, honour `sourced`, empty,
  never-raise); `test_agent_manager.py` (+3: diy surfaces sourced media, non-diy
  none, abstain none); `test_query_answer_route.py` (+2: `_media_ref_responses`).

### Verification performed (machine A, offline — per AGENTS.md I did NOT run pytest)
- `py_compile` over all changed Python files → clean.
- Offline logic smoke via `.venv/bin/python` (no DB): task-key derivation, non-diy
  short-circuit, the guardrail host/subdomain/`sourced` logic (keep path, no DB
  write), and `registry.get('media_curator')` → registered, `parallel_safe`, metrics
  `(link_liveness, relevance, zero_unsourced_urls)`. All pass.
- `frontend/ npm run build` → clean (JSX valid; same pre-existing chunk warning).

## Git flow (owner runs — manual per AGENTS.md)

```
git checkout deployment/sites && git merge --ff-only agents/phase-4 && git push origin deployment/sites && git checkout -b feat/media-curator
```
(The B1 working-tree changes are new/untracked or on files identical between the
two branches, so they carry onto `feat/media-curator`. Then commit B1 there.)

## Commit message (B1)

```
feat(media-curator): Slice B1 — media_refs table (migration 030) + deterministic diy curator + Guardrail zero-unsourced-URL gate + Manager wave-4 wiring + response/UI + seed script + tests
```

## To ship B1 (verification the owner runs)

```
# Machine A
py -m pytest tests/ -q                 # prior 474 + new media tests
py -m ruff check rag/ tests/ api/ db/  # new files clean (ignore pre-existing hits)
# Machine B (corpus)
py scripts/check_migration_details.py --local           # read-only first
py scripts/apply_migration.py db/migrations/030_media_refs.sql
#  → edit scripts/media_refs_seed.json: replace PLACEHOLDER urls with vetted links
py scripts/seed_media_refs.py --local --apply --verified
py scripts/persona_demo.py --local "how do I install a gfci outlet" --personas diy   # videos render
# Deploy: apply 030 on prod RDS by hand, then merge feat/media-curator → deployment/sites (GHA backend+frontend)
```

## Prompt for next session

> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md, and
> docs/agent_architecture.md before touching anything. Restate the current task
> first — AGENTS.md pre-session protocol.
>
> **Media Curator #17 Slice B1 is BUILT on `feat/media-curator` (machine-A compile
> + offline smoke + frontend build green) but NOT verified by pytest, NOT applied
> to any DB, and NOT deployed — do not rebuild it.** Ship it: (1) machine-A
> `py -m pytest tests/ -q` (prior 474 + the new media tests); (2) machine-B apply
> `030_media_refs.sql`, replace the PLACEHOLDER urls in `scripts/media_refs_seed.json`
> with vetted links, `seed_media_refs.py --local --apply --verified`, and run a diy
> query end-to-end (videos render); (3) apply 030 on prod RDS by hand, merge
> `feat/media-curator` → `deployment/sites` (GHA deploys backend+frontend). Plan +
> full detail: `docs/plan_media_curator.md`.
>
> **Then Media Curator Slice B2** (deferred): the `web_search` youtube-only path.
> Load the `claude-api` skill for the current web-search tool id + response shape;
> extend `run_agent` to accept `tools=` (thread through `_dispatch`) + a
> `web_search_tool_result` parser; diy-only, Budget-Governor-capped; same Guardrail
> `check_media_sources` gate.
>
> Carried, still open (all pre-existing, none Media): the query-UX interactive
> click-through eyeball behind Cognito login; a multi-sample live RAGAs baseline +
> repoint `eval_guard` off the stale `ragas_20260531` baseline (STATE punch 3);
> `checksum_sha256` backfill; the `NLI inference failed ('type')` classifier warning;
> q6/Dallas 3-part-PDF retrieval weakness.
