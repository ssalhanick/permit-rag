# Media Curator — Revised Plan (2026-07-25)

_Supersedes the earlier mixed-retrieval vision in this file (YouTube + Reddit
in one lake with prompt-time ordinance precedence). Implements agent #17 +
Slice C against the **segregation** decision._

**Slice plans (implementation detail):**
- [docs/plan_media_curator.md](plan_media_curator.md) — B1 (curated links) / B2 (`web_search`)
- [docs/plan_media_transcripts.md](plan_media_transcripts.md) — C1 (ingest) / C2 (how-to answer)

## North star

DIY users get **sourced how-to help** (vetted video links + transcript-grounded
answers) without letting video/community text ever ground a **compliance**
answer. Compliance faithfulness stays on the authority-only path.

## Architecture (locked)

- **One lake**, two classes: `documents.content_class` ∈ {`authority`, `how_to`}.
- Compliance `match_chunks` → **authority only** (enforced in SQL; 3-arg
  signature kept so migrate/deploy need no ordering).
- DIY how-to → `match_how_to_chunks` / `retrieve_how_to` only.
- **How-to triggers only on diy + compliance abstain** (C2). Never overrides a
  grounded compliance answer. Non-diy never tries how-to.
- URLs only from curated `media_refs` and (later) youtube-scoped `web_search`.
  Guardrail `check_media_sources` hard-gates unsourced URLs.
- Media Curator runs conceptually ∥ generation (Manager wave 4 with
  `_generate` / `_curate_media` / `_how_to_fallback`); best-effort, never fatal.
- One video ≈ one document; captions via `youtube-transcript-api`; embed local
  (`nomic-embed-text-v1.5`), push to RDS (local→prod ingest pattern).
- Jurisdiction: ordinance stays municipality-scoped; how-to media is
  jurisdiction-agnostic (national / NULL jurisdiction applies everywhere).

## What changed from the original vision

| Original idea | Revised choice |
|---------------|----------------|
| Mixed retrieval across ordinance + youtube + reddit; synthesis prompt says ordinance wins | **Segregated** `content_class`; how-to never enters compliance retrieval |
| Reddit + engagement quality scores + age-tiered rescoring | Deferred; YouTube curated allowlist first |
| Super-admin media allowlist dashboard | Seed JSON + scripts for now; dashboard when volume hurts |
| AWS Batch / EventBridge harvest | Local embed → prod RDS until volume requires batch |
| Timestamp deep links (`?t=`) | Still planned (Half 2 polish) |
| Legal review before commercial cite/excerpt | Still blocking for commercial launch |

## Status board

### Done + on prod

- [x] **B1** — `030_media_refs`, deterministic diy-only curator (`rag/agents/media.py`),
  Guardrail zero-unsourced-URL gate, Manager wave-4 wiring, `AnswerResponse.media_refs`,
  QueryPage “How-to videos”, seed script, abstain-still-shows-links for diy
- [x] **C1** — `031_media_transcripts`, `content_class` segregation,
  `ingestion/transcript.py`, `ingest_media_transcripts.py`, RAGAs non-regression
  (avg faithfulness ~0.849, retrieval unchanged)
- [x] **Query-UX** — soft abstain (200), `persona_nudge`, UI `top_k` 8 (enables diy path UX)

### Done in code — ship next

- [ ] **C2 deploy** — `retrieve_how_to`, `Manager._how_to_fallback` (diy compliance-abstain
  → grounded how-to answer), `AnswerResponse.how_to` + `educational_disclaimer`,
  QueryPage “How-To Guide” + amber banner. Pytest + frontend build green; **not
  deployed**. Smoke: diy “install GFCI” → how-to answer; research/contractor unchanged.

### Half 2 — high impact (ordered)

#### H2-1. Corpus growth (unblocks C2 value)

- Expand `scripts/media_refs_seed.json` with vetted DFW-relevant YouTube URLs
- Re-run `seed_media_refs.py` + `ingest_media_transcripts.py` (local embed → prod)
- Extend keyword `task_key` map (Crystallizer target later; rules first)
- **Acceptance:** ≥N task_keys with live captions + at least one diy e2e how-to hit each

#### H2-2. B2 — `web_search` enrichment (coverage gaps only)

- Confirm tool id / `web_search_tool_result` shape via the `claude-api` skill
  (do not hardcode a stale tool id)
- Extend `run_agent` to accept `tools=` + parser; diy-only; Budget-Governor-capped
- Same Guardrail gate; never invent URLs from model memory
- **Acceptance:** gap query gets youtube citation; non-youtube dropped +
  `unsourced_media_url` action item

#### H2-3. Link liveness / eligibility (trust)

- Periodic probe of `media_refs.url`; flag dead links → action queue
- No auto-delete (deactivate / flag for review — governance: never silent drop)
- Optional: refresh `last_verified_at` on pass
- **Acceptance:** dead URL → action item; UI never shows inactive rows

#### H2-4. Citation polish

- Timestamp deep links (`?t=`) when a chunk maps to a transcript offset
- Citations always video title + url; never framed as AHJ authority
- Guardrail: educational disclaimer present on `how_to=True` answers

#### H2-5. Ops / legal (before commercial launch)

- Lawyer review: citing/excerpting YouTube transcripts commercially
- Keep transcript metadata exception documented in README (educational, no
  `effective_date` by design)
- Multi-sample live RAGAs baseline before any faithfulness *gate* (STATE punch 3)

### Absorption into other agents (build the general capability once)

Roughly half of Half-2 is a media-scoped instance of a general agent the
architecture already plans. Absorb these rather than building media one-offs — the
tradeoff is the media benefit waits until that agent lands (all post-Phase-4).

| H2 item | Absorbed into | Stays Media/Phase-4 |
|---------|---------------|---------------------|
| H2-1 corpus growth | — (media content/ops) | all of it |
| H2-2 B2 web_search | the `run_agent tools=` runtime extension is **shared infra** (Web Form Navigator #19 needs it too) | youtube-scoped wiring + guardrail gate |
| **H2-3 link liveness** | **Freshness Watcher (#15)** — it *is* freshness monitoring (probe → liveness diff → action queue, never silent-delete) | — (fully absorbed) |
| H2-4 citation polish | disclaimer-presence → **Guardrail (#4)**; "cite the video, never AHJ authority" → **Citation Verifier (#9, Phase 5)** | timestamp deep-links (`?t=`, media UI) |
| H2-5 ops/legal | multi-sample RAGAs baseline → **Evaluator (#23, Phase 5)** (already STATE punch #2) | legal review = business gate (no phase) |

**Net:** Media Curator's own remaining Phase-4 scope is **C2 deploy → H2-1 corpus →
H2-2 media wiring → timestamp links**. H2-3, most of H2-4, and H2-5's eval piece
move onto Freshness Watcher / Citation Verifier / Evaluator / runtime as those land
(hooks noted in `docs/agent_architecture.md` at #15/#9/#23).

### Explicitly deferred (original vision, not current half)

- Reddit harvest + engagement quality composite scores
- Age-tiered rescoring / weighted eligibility sampling at scale
- Super-admin media allowlist dashboard (seed scripts suffice until volume hurts)
- AWS Batch / EventBridge harvest (keep local→RDS until volume requires it)
- Mixed retrieval + prompt-time ordinance-vs-community conflict resolution
- Numeric claim cross-check vs ordinance (revisit only if reviewer data demands)

## Non-goals

- Separate vector index per media type
- Graph provenance for media (flat metadata is enough — no amendment chains)
- Letting how-to chunks enter compliance retrieval “with a stronger prompt”

## Verification checklist

**Machine A (no corpus):**

```powershell
py -m pytest tests/ -q
py -m ruff check rag/ tests/ api/ db/
cd frontend; npm run build
```

**Machine B / prod:**

- Migrations `030` + `031` applied; seed + transcripts present
- Diy e2e: links render; after C2 deploy, how-to answer replaces empty abstain
- Non-diy personas unchanged (no videos / no how-to answer)
- After any retrieval SQL change: `py -m evaluation.ragas_eval --export --no-answer-cache`

## Migration map

| # | Artifact | Role |
|---|----------|------|
| 030 | `media_refs` | Curated links (B1) |
| 031 | transcripts / `content_class` / `match_how_to_chunks` | Segregation (C1) |
| 032+ | Phase 6 ontology/bids (cascaded) | Unrelated |

## Decisions log (media-specific)

1. **Stage B1 before B2** — `run_agent` has no `tools=` today; curated table is $0 and
   satisfies zero-unsourced-URLs by construction.
2. **Separate tier, never grounds compliance** — owner 2026-07-25; SQL filter, not
   convention.
3. **How-to only on diy compliance abstain** — conservative C2 start.
4. **`media_refs` is data (table), not git fragment files** — links change without a
   code deploy.
5. **Guardrail source gate ships with B1** — B2 has its backstop from day one.
6. **One video ≈ one document** — simple idempotent ingest on video id.
7. **Transcripts are a documented full-metadata exception** — `authority_level=
   educational`, no adoption `effective_date`.

## Open / deferred items (carry from original)

- Legal review of YouTube (and later Reddit) usage rights — blocking before
  commercial launch.
- Whether a media allowlist UI on `/admin/agents` is needed once seed volume grows.
- How flagged dead/outdated media items surface next to existing LLM-response
  grading in the reviewer dashboard.
```
