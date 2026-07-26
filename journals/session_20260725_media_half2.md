# Session 2026-07-25 (cont.) — Media Curator Half-2 + query-path fixes

Continuation of the Media Curator work. Machine A (repo, macOS, `.venv`); DB/corpus
ops on machine B; prod = RDS.

## Task (restated)
Deploy the query-UX/C2 work, then Media Curator Half-2 (corpus + B2 + scaling).
Along the way: fix per-project role/jurisdiction, add a settings page, and enable
channel-scale ingest.

## Accomplished

### Verified C2 deploy → caught + fixed a prod regression
C2 (how-to answers) + persona/jurisdiction fixes + semantic links were all found
already on `deployment/sites` (prod). Verifying `/api/documents` surfaced a **live
ValidationError**: the transcript ingest added docs with `authority_level=
'educational'` / `doc_type='how_to_video'`, but `DocumentSummaryResponse` had
`Literal` enums without them. Fix: `list_documents` defaults to
`content_class='authority'` (compliance corpus views exclude how-to) + the response
fields relaxed to `str` (crash-safe). Regression test added.

### Query-path fixes (persona / jurisdiction / settings)
- **Persona wasn't routing** even when set: `_resolve_persona` did an exact match.
  Added `_normalize_persona` (trim/lowercase/hyphen→underscore) → `DIY`,
  `hiring-contractor`, whitespace all resolve. Diagnostic log in `_route_prompt`.
- **Jurisdiction from the project**: `_load_project_context` moved to **wave 1** so
  `_resolve_municipality` falls back to the project's stored municipality/address —
  a project-scoped query is jurisdiction-aware from `project_id` alone.
- **Kickoff hyphen bug**: `hiring-contractor` → `hiring_contractor` (enum value).
- **Project Settings page** (`/projects/:id/settings`) — edit all fields incl. role.

### Half-2 absorption documented
`docs/media-curator-plan.md` gained an "Absorption into other agents" table +
`docs/agent_architecture.md` one-line hooks at #15 (Freshness → link liveness), #9
(Citation Verifier → media citations), #23 (Evaluator → multi-sample RAGAs). H2-2's
`run_agent tools=` flagged as shared runtime infra (Phase 9 too).

### H2-6.1 semantic links (deployed)
`_curate_media` now merges curated `task_key` links with **semantic** links —
videos behind the retrieved how-to transcripts (`fetch_media_refs_for_how_to_docs`
joins chunk `doc_id`→`media_refs` via `source_url`), deduped, gated. The how-to
retrieval is cached on `_PlanState` and shared with `_how_to_fallback`. **Any
ingested video now surfaces with no hand-assigned task_key** — the scaling unlock.

### H2-6.2 channel crawl (built; deploy-pending)
Vet a channel, auto-enumerate uploads. Migration `032_media_channels.sql`
(`media_channels` + `media_refs.channel_id`); `ingestion/youtube_channel.py`
(free RSS enumeration + `resolve_channel_id` from `@handle`/URL);
`scripts/crawl_media_channels.py`; db.client channel helpers.

### Throttle + block-aware ingest
`fetch_transcript` distinguishes a **block** (`TranscriptBlocked`) from no-captions,
retries transients; `ingest_media_transcripts.py` gained `--delay` throttle +
`--max-blocks` circuit-breaker.

### sync_how_to_to_prod (the block workaround)
YouTube IP-blocks channel-scale transcript fetching (the documented H2-6 ops
threshold). `scripts/sync_how_to_to_prod.py` copies **already-embedded** how-to
data (channels + refs + docs + chunks-with-vectors) from a source db → prod,
**no YouTube, no re-embed**. Used it to put **This Old House (18 videos / 128
chunks) on prod** — a diy query now hits them semantically. Idempotent, transactional.

## Deploy state
- **On prod (`deployment/sites`):** C2, `/api/documents` fix, persona/jurisdiction/
  settings fixes, semantic links (H2-6.1). Migration `032` applied on prod (for the
  sync). This Old House data synced to prod.
- **Built, NOT yet merged to `deployment/sites`:** channel crawl (committed on
  `agents/phase-4`: `63a2bd2`+`912bce5`), throttle + sync scripts (uncommitted). All
  ops tooling — not on the query hot path, so prod *works*; merge is for repo parity.

## Findings worth keeping
1. **YouTube blocks channel-scale transcript fetch by IP** (cloud/campus). The 4
   seed videos worked; a burst of ~15 tripped it. Mitigations: throttle (partial),
   residential IP (works now), **proxy** (`YOUTUBE_PROXY_*`, the scalable fix, not
   yet wired). The **sync script decouples embed-location from the block** — embed
   wherever you can, push the vectors up.
2. **Semantic links make task_key optional** — retrieval is over embeddings, so
   crawled/ingested videos surface without per-video keying. task_key survives as a
   fast-path/boost.
3. **B2 ≠ Freshness Watcher.** Link liveness (H2-3) → Freshness #15; B2 web_search
   is a Media Curator coverage tool (Phase 4/Half-2); only `tools=` is shared infra.

## Commit messages (this session)
```
fix(api): /api/documents ValidationError on how-to docs — authority-only corpus list + tolerant DocumentSummaryResponse
fix(projects): tolerant persona resolution + jurisdiction from project municipality/address + kickoff hiring_contractor + Project Settings page
feat(media-curator): H2-6.1 semantic links (fetch_media_refs_for_how_to_docs; cached shared how-to retrieval)
feat(media-curator): H2-6.2 channel crawl (media_channels/032 + RSS + @handle resolver)
feat(media-curator): throttle + block-aware ingest (TranscriptBlocked; --delay/--max-blocks)
feat(media-curator): sync_how_to_to_prod (copy embedded how-to data local→prod, no re-fetch)
```

## Prompt for next session
> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md, and
> docs/agent_architecture.md + docs/media-curator-plan.md before touching anything.
> Restate the current task first (AGENTS.md pre-session protocol).
>
> **Close Phase 4.** All Media Curator user-facing work is on prod (B1 links, C1
> transcripts, C2 how-to answers, semantic links, This Old House channel data).
> Remaining to close: (1) commit the throttle + `sync_how_to_to_prod` scripts and
> ff-merge `agents/phase-4` → `deployment/sites` so the deployed branch carries the
> channel-crawl + throttle + sync ops tooling (schema `032` already on prod; these
> are not on the query hot path, so it's repo parity); (2) `py -m pytest tests/ -q`
> green; (3) move Media Curator / Phase 4 to **Completed** in README. Do NOT rebuild
> anything — it's all committed/working.
>
> **Deferred (NOT Phase 4 blockers), captured in docs/media-curator-plan.md:** B2
> `web_search` (needs the `claude-api` skill + `run_agent tools=`); link liveness →
> Freshness Watcher #15; proxy support (`YOUTUBE_PROXY_*`) for at-scale ingest;
> multi-sample RAGAs baseline → Evaluator #23.
>
> **Then Phase 5** (course cut line, agent_architecture.md): answer agents (Query
> Deconstructor #5, Citation Verifier #9, Permit Strategy #11) + Evaluator #23 +
> Performance Review #24 + feedback UI + dashboard v2 + Field Ontology core (items
> 1–3). Start with the Evaluator + feedback loop (they anchor everything else) and
> the multi-sample RAGAs baseline (also STATE punch #2).
