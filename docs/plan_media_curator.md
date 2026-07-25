# Plan — Media Curator (agent #17), Phase 4 second pass

_Drafted 2026-07-25. Branch: `feat/media-curator` off `deployment/sites`._

## Goal (from docs/agent_architecture.md)

Agent #17. Sourced how-to video links for the **`diy`** answer path. **Never emits
a URL from model memory.** Two sourced paths only:

1. **Curated `media_refs` table** — task → vetted URL → jurisdiction relevance →
   last-verified. A deterministic DB lookup.
2. **`web_search`** with `allowed_domains: ["youtube.com"]` + citations.

**Guardrail rejects any URL from neither.** Metric contract: link liveness,
relevance, and **zero unsourced URLs (hard gate)**. Runs **∥ Answer Generator**
on the diy path (media lookup doesn't depend on the prose).

## Key constraint discovered in the code

`rag/agent_runtime.run_agent` (the single Anthropic call site) has **no `tools=`
parameter** — it only routes to `messages.parse` / `messages.create` with a fixed
kwargs set (`rag/agent_runtime.py:409-426`). So:

- The **curated-table path needs no runtime change** — pure `db/client` lookup,
  no LLM, **$0**, and it satisfies the hard gate by construction (every URL is a
  vetted row).
- The **`web_search` path needs the runtime to learn `tools=`** + parsing of
  `web_search_tool_result` blocks. Bigger surface, real cost, and the exact tool
  id / response shape must be confirmed against the **`claude-api` skill** before
  building (do not hardcode `web_search_20260209` from the doc without checking).

**→ Stage it.** Ship the deterministic table path first (B1); add web_search as an
opt-in second slice (B2). This mirrors the project's deterministic-first rule and
gets a demo-able, zero-cost, zero-unsourced-URL feature landed without touching
the call site.

---

## Slice B1 — curated `media_refs` + deterministic curator + Guardrail gate + diy wiring

### 1. Migration `030_media_refs.sql` (additive, idempotent)

```sql
CREATE TABLE IF NOT EXISTS media_refs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_key        text NOT NULL,          -- normalized task, e.g. 'install_gfci_outlet'
    title           text NOT NULL,
    url             text NOT NULL,
    provider        text NOT NULL DEFAULT 'youtube',  -- host allow-list anchor
    jurisdiction    text,                   -- nullable: national how-tos apply everywhere
    relevance_note  text,
    last_verified_at timestamptz,
    active          boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_media_refs_task ON media_refs (task_key) WHERE active;
```

- Seed a handful of vetted DFW-relevant rows (permit-adjacent how-tos) so the demo
  shows real links.
- Mirror enum/constraint style from `db/schema.sql`; keep it in `schema.sql` too.

> **Migration-number decision (needs owner OK).** `030` is the next free number,
> but `docs/agent_architecture.md:648` reserved `030_ontology_and_bids` for
> **Phase 6** (unshipped, nothing deployed at 030). Cleanest: **take `030` for
> `media_refs` and re-label the planned Phase-6 migration `031`.** Update the doc's
> numbering note. (Same additive-cascade convention used for 028/029.)

### 2. `db/client.py` — one reader

`fetch_media_refs(task_key: str | None, jurisdiction: str | None, limit: int = 3)`
→ active rows for the task, jurisdiction-matching first then national (NULL),
ordered by `last_verified_at DESC`. No writes. All access through `db/client.py`
per AGENTS.md (no inline supabase).

### 3. `rag/agents/media.py` — the curator (deterministic, no LLM)

- `curate(query, *, persona, jurisdiction, permit_types) -> list[MediaRef]`.
- **Only runs for `persona == "diy"`** — returns `[]` otherwise.
- Derive `task_key` from the query + permit types (a small keyword map first — a
  Crystallizer-friendly rule table; the LLM task-extraction is a B2 nicety).
- Returns vetted rows from `fetch_media_refs`. Never fabricates a URL.
- Import boundary OK: `rag/agents/ → rag/, db/, audit/, stdlib`.

### 4. `rag/agents/guardrail.py` — `check_media_sources`

- `check_media_sources(items, *, allowed_hosts={"youtube.com"}, run_id, entity_id)
  -> list[MediaRef]`: **drops** any item whose URL host is not youtube.com **and**
  not a known `media_refs` row; returns the surviving sourced list.
- On a drop, file a deduped `unsourced_media_url` action item (mirrors
  `check_truncation`: `upsert_action_item`, non-blocking, never raises). On the B1
  DB path nothing should ever drop — the gate matters once B2/web_search can
  propose model-emitted URLs. Ship the gate now so B2 has its backstop (same
  pattern as the truncation trip shipping with the Router).

### 5. Wire into the Manager diy path

- Persist the **resolved persona** on `_PlanState` in `_route_prompt`
  (`manager.py:431`) so media doesn't re-resolve it.
- Add `_curate_media(state)` and put it in **wave 4 alongside `_generate`**:
  `_PLAN` becomes `(..., (_generate, _curate_media))` (`manager.py:582`). Steps in
  a wave are independent; the current executor runs them sequentially, which is
  fine for a ~$0 DB lookup (true asyncio fan-out is the doc's future latency lever,
  not needed here).
- `_curate_media`: skip on `state.abstained`; skip unless resolved persona is
  `diy`; call the curator, pass results through the Guardrail gate, store on
  `state.media_refs`.
- Thread `media_refs` through `ManagerResult` + `_assemble` (`manager.py:635`).

### 6. Response surface

- `api/schemas.py`: add `MediaRefResponse` (title, url, provider, jurisdiction,
  relevance_note) and `AnswerResponse.media_refs: list[MediaRefResponse] = []`
  (default empty — non-diy and abstains carry none).
- `api/routes/query.py`: map `ManagerResult.media_refs` onto the response (next to
  where `persona_nudge` / `abstained` are set).
- **Frontend** (`QueryPage.jsx`): a "📺 How-to videos" section under the answer,
  rendered only when `media_refs.length > 0`. Small, same pattern as the citations
  block. (Can land in B1 or a fast follow.)

### 7. Tests (machine A, mocked)

- `test_media_curator.py`: diy → returns vetted rows; non-diy → `[]`; abstain →
  skipped; task_key derivation.
- `test_guardrail.py` (extend): `check_media_sources` drops a non-youtube /
  non-`media_refs` URL and files the action item; keeps a youtube row; never
  raises.
- `test_query_answer_route.py` (extend): a diy query surfaces `media_refs`; a
  non-diy query returns `[]`; **zero unsourced URLs** assertion (the hard gate).
- Manager wiring: `_curate_media` runs in wave 4, doesn't run on abstain.

### 8. Docs (post-session)

STATE.md (module table + decisions + migration table + next tasks), README
(Planned → Completed for Media Curator core), this file, journal.

---

## Slice B2 — `web_search` enrichment (opt-in, later; needs the runtime extension)

Only when the curated table has coverage gaps. Requires, in order:

1. **Load the `claude-api` skill** — confirm the current web-search server-tool id
   and the `web_search_tool_result` response shape. Do not build from the doc's
   `web_search_20260209` string alone.
2. **Extend `run_agent`** to accept `tools=` and thread it through `_dispatch`
   (`agent_runtime.py:409`) — the single call site stays single. Add a
   `web_search_tool_result` parser that extracts `{title, url}` + citations.
3. **Curator B2 path**: `web_search` with `allowed_domains:["youtube.com"]`,
   `diy`-only, **Budget-Governor-capped** (it's the one paid step here; cost model
   pegs it ~$0.0015/diy query).
4. Everything flows through the **same Guardrail gate** — now doing real work,
   dropping any model-proposed URL that isn't youtube-sourced.
5. Autonomy: read-only enrichment, inline in the request → effectively **L3**
   (like answer-path agents); no approval gate, only the cost cap.

---

## Acceptance (docs/agent_architecture.md verification)

- `py -m pytest tests/test_media_curator.py -v` — diy surfaces sourced videos;
  **zero unsourced URLs** (hard gate) on both paths.
- Guardrail drops any non-sourced URL and files an action item.
- Non-diy / abstain / no-coverage → empty `media_refs`, no error, no fabricated
  link.
- Machine B: apply `030`, seed rows, run a diy query end-to-end, confirm real
  youtube links render.

## Non-goals / deferred

- Link-liveness monitoring (a Freshness-Watcher-style job) — metric is defined;
  the checker is a later slice.
- LLM task-key extraction — keyword rule table first (Crystallizer target).
- Full chat-thread `QueryPage` redesign — still deferred (owner chose quick-wins).
