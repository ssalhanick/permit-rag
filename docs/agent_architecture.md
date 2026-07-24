# Agent Architecture, Prompt Routing, Feedback, Autonomy & Cost — permit_rag

## Context

permit_rag has ~8 single-purpose "proto-agents" (`rag/permit_classifier.py`, `rag/jurisdiction_resolver.py`, `rag/conflict_detector.py`, `rag/reranker.py`, `rag/design_intent.py`, `rag/mini_rag.py`, `rag/project_context.py`, `rag/generator.py`) wired together by hand in `api/routes/query.py`. There is no orchestrator, no per-agent telemetry, no per-agent metrics, no way for a human to correct an agent, no autonomy model, and no way to turn repeated LLM work into deterministic code.

Six defects block the rest:

1. **`audit/logger.py`, `audit/anomaly.py`, `audit/provenance.py` are 0-byte stubs.** Nothing records per-call tokens, latency, cost, or human corrections. Evaluation, optimization, feedback, autonomy gating, and cost control all read from a trace store that does not exist. (Fix in Phase 0.)

2. **Reranker-rejected chunks are billed to the model.** `rag/reranker.py:100` marks low-scoring chunks `filtered_out=True`, and `rag/retriever.py:243` exposes a `passing_chunks` property for exactly this purpose. `rag/conflict_detector.py:105` filters correctly. But `api/routes/query.py:423` passes `result.chunks` — **all of them** — into `generate_answer`, and `_format_chunks_for_prompt` (`rag/generator.py:239`) has no filter. Rejected chunks are paid for on every query *and* fed to the model as context, including superseded documents the reranker demoted to `retrieval_weight=0.1`. A one-line fix, worth ~15–20% of input tokens plus a quality improvement.

3. **Corpus metadata is materially wrong, and it drives retrieval.** Audit of `documents/metadata/*.json` (27 docs): **27/27 have `effective_date: null`** (AGENTS.md forbids ingesting without it); **5 have `doc_type: null` and `authority_level: null`** (`mansfieldtx-tx-1/2`, `parker-tx-1`, `plano_3`, `plano_4`) while `db/schema.sql:86-87` declares both `not null`; the same 5 have **zero `subject_tags`**; and `ingestion/harvester.py:280` infers tags from **only the first 2000 chars** — the cover page of a multi-hundred-page code.

4. **Prompt management is a single unversioned LLM-generated blob.** `projects.custom_system_prompt` (migration 020) is free text synthesized once by the kickoff chat and appended in `_build_system_prompt` (`rag/generator.py:73`). Unversioned, unevaluated, un-rollback-able, an injection surface, applied identically to every query type — and it **defeats prompt caching across projects**, so `cache_read_input_tokens` is 0 on every project-scoped query.

5. **There is no feedback path.** When an answer is wrong, nothing captures it, attributes it, or feeds it back.

6. Agent selection, model choice, and context assembly are hardcoded, so token spend is unmanaged and unmeasured.

**Decisions carried in from planning:**
- Document the full architecture; ship a demo-able slice first (course at Week 10, Jul 21–Aug 1).
- In-house Python agents on the Anthropic SDK for the RAG core; Claude Agent SDK only for the browser/form agent.
- Form filling: agent fills → diff/preview → user approves → agent submits. Never auto-submits.
- Optimizer/Crystallizer: propose-only. They open PRs. A human merges.

---

## Terminology

**"Call site"** — a specific place in the code where a function is invoked. Two places construct an Anthropic client directly today: `rag/generator.py:402` and `rag/design_intent.py:147`. Each independently decides model, `max_tokens`, caching, retries, and whether anything is logged — and `design_intent.py` already violates the AGENTS.md rule that all model calls go through `generator.py`. If 26 agents each add their own, that's 26 places to fix when the model ladder changes and 26 chances to forget a trace. `rag/agent_runtime.py` makes it one.

**"ReAct"** — Reason → Act → Observe, looped: the model reasons about what to do, calls a tool, observes the result, reasons again. Contrast with a fixed pipeline where the call sequence is hardcoded. Detailed section below.

---

## Roster — 26 agents + 2 services

### Tier 0 — control
| # | Agent | Owns | Module |
|---|-------|------|--------|
| 1 | **Manager** | Intent routing, plan build, delegation, result assembly. Sees artifact IDs + summaries only. | `rag/agents/manager.py` |
| 2 | **Prompt Router** | Composes the system prompt per request from versioned fragments. | `rag/agents/prompt_router.py` |
| 3 | **Budget Governor** | Per-request token cap, model ladder, degradation. Not an LLM. | `rag/agents/budget.py` |
| 4 | **Guardrail** | Grounding floor (`api/routes/query.py:40`), PII, injection defense, no-auto-submit, disclaimer enforcement. | `rag/agents/guardrail.py` |

### Tier 1 — answer path
| # | Agent | Owns | Module |
|---|-------|------|--------|
| 5 | **Query Deconstructor** | Compound question → sub-questions + filters. | `rag/agents/deconstructor.py` |
| 6 | **Jurisdiction** | Wraps `rag/jurisdiction_resolver.py`. LLM only on ETJ/county overlap. | wrap existing |
| 7 | **Retrieval Strategist** | top_k / hybrid / filters; re-retrieve on guard failure. | `rag/agents/retrieval.py` |
| 8 | **Answer Generator** | Exists — `rag/generator.py::generate_answer`. | existing |
| 9 | **Citation Verifier** | Deterministic span-match first; LLM entailment on leftovers. | `rag/agents/citation_verifier.py` |
| 10 | **Conflict Analyzer** | Semantic tier C atop `rag/conflict_detector.py`. | extend existing |
| 11 | **Permit Strategy** | Project context → permit set, sequencing, fees. | `rag/agents/permit_strategy.py` |
| 12 | **Instructions** | README TODO — design intent → step-by-step. Persona-aware. | `rag/agents/instructions.py` |

### Tier 2 — action agents
| # | Agent | Owns | Module |
|---|-------|------|--------|
| 13 | **Corpus Metadata Validator** | Verifies uploaded/pulled doc metadata is *true*, not just present. | `ingestion/metadata_agent.py` |
| 14 | **Document Intake** | Wraps `harvester.py`, `page_crawler.py`, `governance.py`. Proposes supersede. | `rag/agents/intake.py` |
| 15 | **Corpus Freshness Watcher** | Scheduled re-pull + checksum diff + flag. | `rag/agents/freshness.py` |
| 16 | **Bid Evaluator** | Parse + score an uploaded contractor bid. | `bids/evaluator.py` |
| 17 | **Media Curator** | Sourced how-to video links. Never emits a URL from model memory. | `rag/agents/media.py` |
| 18 | **PDF Form** | AcroForm/OCR permit PDFs → schema → fill → flag unknowns. | `forms/pdf_agent.py` |
| 19 | **Web Form Navigator** | Municipal e-permit portals. Claude Agent SDK. Replayable macro. | `forms/web_agent.py` |
| 20 | **Design/Commerce** | Wraps `design_intent.py` + `commerce/`. Registered by `api/`. | tool registration |
| 21 | **Project Memory** | Durable per-project facts. Extends `rag/project_context.py`. | `rag/agents/memory.py` |
| 22 | **Clarification** | Ask-vs-guess. Reuses the kickoff pattern at `rag/generator.py:473`. | `rag/agents/clarify.py` |

### Tier 3 — meta
| # | Agent | Owns | Module |
|---|-------|------|--------|
| 23 | **Evaluator** | Per-agent metric contracts. | `evaluation/agent_eval.py` |
| 24 | **Performance Review** | Attributes feedback to the responsible agent + step, with evidence. | `evaluation/perf_review.py` |
| 25 | **Optimizer** | Offline. Traces + corrections → proposed fixes → eval → PR on win. | `evaluation/optimizer.py` |
| 26 | **Crystallizer** | Offline. Stable trace clusters → deterministic artifact + tests → PR. | `evaluation/crystallizer.py` |

### Services
| Service | Owns | Module |
|---------|------|--------|
| **Trace Collector** | Per call: tokens in/out/cached, latency, cost, model, fragment IDs, input hash, outcome, correction. | `audit/logger.py` |
| **Field Ontology** | Canonical vocabulary: project fact ↔ form field ↔ bid line item. | `forms/ontology.py` |

---

## Cost model

### Measured inputs
- `CHUNK_SIZE = 1500` chars ≈ **375 tokens/chunk** (`ingestion/chunker.py:31`), plus ~40 tokens of per-chunk metadata header from `_format_chunks_for_prompt`.
- `top_k` default **5** (`api/schemas.py:51`); `rag/pipeline.py` test queries use **10**. Both modeled.
- Base `SYSTEM_PROMPT` ≈ 400 tokens; project context ≈ 150; question ≈ 30.

### Output tokens are persona-dependent — and today's cap will truncate

The current `SYSTEM_PROMPT` explicitly asks for brevity ("1-2 sentences… 1-2 short bullet points", `rag/generator.py:56-66`), so ~400 output tokens is right for the **baseline**. It is wrong for the agent version: the persona fragments deliberately demand more.

| Persona | Expected output | Why |
|---------|----------------|-----|
| `contractor` | ~350 | Citation-led, no scaffolding |
| `research` | ~500 | Neutral comparison |
| `hiring_contractor` | ~1,300 | Layman explanation + labor/material split + questions to ask + red flags |
| `diy` | ~1,500 | Steps + tool list + tips + safety checkpoints + media refs |
| Instructions agent (#12) | ~2,000+ | Step-by-step is the entire deliverable |

**This exposes a defect the plan must fix:** `generate_answer` hard-codes `max_tokens=1024` (`rag/generator.py:339`). A `diy` or `hiring_contractor` answer will hit that ceiling and truncate — mid-checklist, mid-red-flag-list. Truncation in a compliance answer is a bad failure, and it will look like a quality regression when it's a config bug. `max_tokens` becomes persona/intent-aware in Phase 4, and `stop_reason == "max_tokens"` becomes a Guardrail trip that files an action item.

**Output is priced 5× input.** Persona choice is therefore a first-order cost driver, not a rounding error.

### Baseline today — one `/query/answer` call, haiku-4-5 ($1 in / $5 out per 1M)

| top_k | Input tokens | Output | Cost |
|-------|-------------|--------|------|
| 5 | ~2,655 | 400 | **$0.0047** |
| 10 | ~4,730 | 400 | **$0.0067** |

If ~30% of retrieved chunks are `filtered_out` (defect #2), roughly **$0.0006–0.0012/query is spent on chunks the reranker already rejected**.

### Agent run — Balanced config (haiku orchestration, sonnet-5 generation), by persona

Deterministic steps cost **$0**. Citation Verifier input scales with answer length — more claims to check.

| Step | Model | `contractor` | `research` | `hiring_contractor` | `diy` |
|------|-------|-------------|-----------|--------------------|-------|
| Manager plan | haiku | $0.0020 | $0.0020 | $0.0020 | $0.0020 |
| Prompt Router | *deterministic* | $0 | $0 | $0 | $0 |
| Query Deconstructor | haiku | $0.0018 | $0.0018 | $0.0018 | $0.0018 |
| Jurisdiction / Retrieval / Guardrail / Conflict A-B | *deterministic* | $0 | $0 | $0 | $0 |
| **Answer Generator** (4,730 in) | sonnet-5 | $0.0195 | $0.0217 | $0.0337 | $0.0367 |
| Citation Verifier | haiku | $0.0028 | $0.0028 | $0.0048 | $0.0048 |
| Media Curator *(diy only)* | *web_search* | — | — | — | $0.0015 |
| Manager assemble | haiku | $0.0016 | $0.0016 | $0.0016 | $0.0016 |
| **Total** | | **$0.0277** | **$0.0299** | **$0.0439** | **$0.0484** |
| **With fragment cache** | | **$0.0167** | **$0.0189** | **$0.0329** | **$0.0374** |

**Blended** at a plausible mix (40% diy, 30% hiring_contractor, 20% research, 10% contractor): **~$0.030/query**, or **~$0.0296 with cache** — roughly **4.5× the top_k=10 baseline**.

*(Correction to an earlier estimate in this plan: modeling every persona at 400 output tokens gave ~$0.019 blended. That was too optimistic. The personas that create the most user value are exactly the ones that generate the most output, and output costs 5× input.)*

Economy config (all-haiku generation) lands near **$0.019 blended**; Premium (opus Manager) near **$0.038**.

**Recommendation: start Balanced, measure, then push steps down the ladder.** The Crystallizer's job is turning the paid rows into $0 rows.

### The uncomfortable finding
**Retrieved chunks dominate input cost and they do not cache** — different query, different chunks. The fragment library caches; the corpus does not (except on follow-up turns in one conversation). So the real generation-cost levers, in order of impact:

1. **Drop `filtered_out` chunks** — free, already-computed, ~15–20% of input. Fix in Phase 0.
2. **top_k** — linear. 10 → 5 halves chunk cost.
3. **Model tier for generation** — 3× spread haiku → sonnet.
4. **Output tokens** — priced 5× input. `effort: low` and verbosity fragments matter more than they look.
5. Fragment caching — real, but bounded to the stable prefix.

### Non-query workloads

| Workload | Unit | Est. cost | Notes |
|----------|------|-----------|-------|
| Metadata validation | per document | ~$0.035 | ~20 sampled chunks (7,500 in) + 800 out on sonnet |
| **27-doc backfill** | one-time | **~$0.95, or ~$0.48 batched** | Trivial. Do not optimize this. |
| Bid evaluation | per bid | ~$0.05 | ~10-page PDF, structured extraction |
| Performance Review | per thumbs-down | ~$0.03 batched | Full trace on opus; low volume by nature |
| Web Form Navigator | per portal session | **$0.50–$2.00** | Wide error bars. Screenshots are image tokens; multi-turn loop with growing context. **10–100× a query — the one workload that needs a hard task budget.** |
| Optimizer / Crystallizer | nightly | budget-capped | Batch API, set a ceiling |

### Monthly projection (Balanced + cache, ~$0.0296 blended/query)

| Queries/mo | Query cost | + corpus ops | Total |
|-----------|-----------|--------------|-------|
| 500 (demo) | $14.80 | ~$1 | **~$16** |
| 5,000 | $148 | ~$10 | **~$158** |
| 50,000 | $1,480 | ~$50 | **~$1,530** |

Add ~$1–$4 per portal submission if the Web Navigator ships.

### Cost factors — the full list
1. **Chunks per query** (`top_k` × `CHUNK_SIZE`) — dominant input cost, does not cache across queries.
2. **Output length, driven by persona** — priced 5× input. `diy` and `hiring_contractor` cost ~1.8× `contractor` on the same question.
3. **`filtered_out` leakage** — pure waste today.
4. **Model tier per step** — 5× spread haiku → opus, both directions.
5. **Number of LLM steps per run** — orchestration overhead; deterministic steps are free.
6. **Cache hit rate on the fragment library** — only if it clears the 2048/4096-token minimum.
7. **Deterministic-hit-rate** — the Crystallizer KPI; a crystallized step costs $0.
8. **Retry/repair rate** — structured outputs eliminate JSON-repair retries.
9. **Batch vs. interactive** — 50% off for anything offline.
10. **Replan/guard-trip rate** — a failed guard triggering re-retrieval + regeneration roughly doubles that query.
11. **ReAct iteration count** — every loop resends accumulated context.
12. **Truncation retries** — a `max_tokens` cut requiring a re-ask costs the full query twice. Fixing the 1024 cap is a cost item, not just a quality one.

**Every number above is an estimate until Phase 0 ships.** The trace store is what replaces this model with measurement, and the dashboard's cost tab is where it lands.

---

## ReAct — where it applies, and where it deliberately doesn't

**Modern form, not the 2022 form.** Do not write `Thought:/Action:/Observation:` prompt scaffolding. The SDK tool runner *is* the ReAct loop (request → `tool_use` → execute → `tool_result` → repeat), and `thinking: {"type": "adaptive"}` interleaves reasoning between tool calls natively on Opus 4.8 / Sonnet 5. Hand-rolled scratchpads are obsolete and cost tokens for nothing.

### Where ReAct is genuinely used — 4 places

| Agent | Why it needs a loop | Bound |
|-------|--------------------|-------|
| **Manager** (#1) | Cannot know the plan up front. Observes each artifact summary and decides the next step; a bid upload mid-conversation changes the route. | `max_iterations=6`, `task_budget` |
| **Web Form Navigator** (#19) | Textbook case — observe screenshot/DOM, act, observe result. No portal is knowable in advance. | `max_iterations=30`, `task_budget`, context editing |
| **Retrieval Strategist** (#7) | Bounded loop only on guard failure: retrieve → observe grounding score → widen filters → retry. | `max_iterations=2`, then give up and say so |
| **Metadata Validator** (#13) | Mild: sample chunks → observe ambiguity → sample more from a different section. | `max_iterations=3` |

### Where it is deliberately avoided
Deconstructor, Citation Verifier, Permit Strategy, Bid extraction, Prompt Router, Instructions — **single-shot structured extraction**. A ReAct loop here adds a full round trip with re-sent accumulated context for no decision that needs making.

**ReAct is a cost multiplier.** Each cycle resends everything accumulated so far. A 6-iteration Manager loop with a growing transcript can cost more than the generation it's orchestrating. This is why the Manager sees `ArtifactRef` summaries instead of raw text — it directly bounds ReAct's blast radius.

**The Crystallizer is anti-ReAct by design.** Its whole thesis is converting stable reasoning loops into deterministic paths. A rising deterministic-hit-rate means ReAct is being used in fewer places over time — that is the intended direction, not a regression.

### Parallelism — yes, and it's the main latency lever

ReAct is sequential by nature, but most of the work in a run is not. Two mechanisms:

- **Model-driven fan-out** — one assistant message can contain multiple `tool_use` blocks. Execute them concurrently and return **all** `tool_result` blocks in a *single* user message. Splitting results across multiple messages silently trains the model to stop parallelizing — a real footgun worth a test.
- **Code-driven fan-out** — `asyncio.gather` in the Manager for steps it already knows are independent. No model round trip needed to decide.

**What runs in parallel:**

| Group | Steps | Gate |
|-------|-------|------|
| Pre-retrieval | Jurisdiction ∥ Permit classification ∥ Project Memory load ∥ Prompt Router | all deterministic, all independent |
| Retrieval fan-out | one retrieval per sub-question from the Deconstructor | the biggest win — a 3-part compound question does 3 retrievals concurrently |
| Post-generation | Citation Verifier ∥ Conflict Analyzer | both read (answer + chunks), neither reads the other |
| DIY enrichment | Media Curator ∥ Answer Generator | media lookup doesn't depend on the prose |
| Bid analysis | Completeness ∥ Pricing ∥ Red flags | fully independent by construction |

**Strictly sequential:** retrieve → generate; generate → verify citations; extract → analyze (bids); observe → act (Web Navigator).

**What parallelism does and does not buy.** It does **not** reduce token cost — same tokens, same price. It buys **latency**, which for a `diy` answer with 3 sub-questions is roughly a 2–3× wall-clock improvement. It also indirectly reduces cost by cutting ReAct iterations: fan-out in one turn beats three sequential Manager loops, each of which resends the accumulated transcript.

**Two implementation cautions:**
- **Connection pool sizing.** Parallel retrievals hit pgvector concurrently. `psycopg-pool` is already a dependency; the pool must be sized for `max_parallel_steps`, or fan-out just queues on the DB and the latency win evaporates.
- **Concurrent cache writes.** N parallel requests sharing a prefix all pay full price — none can read what the others are still writing. On a fan-out with a shared cached prefix, fire one request, await its first streamed token, then fire the rest.

---

## Autonomy levels — human-in-the-loop → agent takes the wheel

Yes, and it should be per-agent, dashboard-controlled, and **ceiling-clamped**.

### Four levels
| Level | Behavior |
|-------|----------|
| **L0 — Suggest** | Agent produces a proposal. A human must act on it. |
| **L1 — Approve** | Agent stages a change; human clicks approve; agent executes. |
| **L2 — Auto + notify** | Agent acts, writes an action item for after-the-fact review. Reversible. |
| **L3 — Auto** | Agent acts silently; logged only. |

Stored in `agent_autonomy` (`agent_name`, `current_level`, `max_level`, `ceiling_reason`, `updated_by`, `updated_at`). **Enforced in `rag/agent_runtime.py`** — so the check exists from Phase 1 and no agent can bypass it — and edited from the dashboard.

### Ceilings the dashboard cannot override

| Agent | Ceiling | Why |
|-------|---------|-----|
| Document Intake — **source URL change** | **L0** | AGENTS.md: "Source URL changes → flag for human review, never auto-update." |
| Document Intake — supersede/repeal | **L1** | AGENTS.md: "Never delete a document — supersede or repeal only." |
| Metadata Validator — doc_type / effective_date / supersession | **L1** | Changes retrieval behavior and governance state |
| Metadata Validator — enum + completeness fixes | L2 | Mechanical, reversible |
| **Web Form Navigator — submit** | **L1** | Irreversible filing with a government body. Non-negotiable. |
| Web Form Navigator — navigate/fill | L2 | Reversible drafting |
| Optimizer / Crystallizer | **L1** | An explicit planning decision: propose-only, PR + human merge |
| Bid Evaluator | L3 | Read-only analysis, no side effects |
| Guardrail | **L3 required** | It's a blocker, not a proposer — a human approving each guard check defeats it |
| Answer-path agents (5–12) | L3 | Inline in a request; approval is meaningless |
| Freshness Watcher — detect | L3 | Detection is free |
| Freshness Watcher — re-ingest | L1 | Touches the corpus |
| PDF Form — fill | L2 | Produces a draft |
| Performance Review — high confidence | L2 | |
| Performance Review — low confidence | **L0** | Never silently record blame it isn't sure of |

The dashboard shows a slider per agent, clamped, with the ceiling reason displayed on hover. An autonomy control that can be turned all the way up on a government-filing agent is a liability, not a feature.

### Graduated autonomy — earned, not guessed
The scorecard already tracks acceptance and correction rate. The dashboard surfaces eligibility: *"Metadata Validator: 98% acceptance over 212 proposals — eligible for L2."* You promote on evidence rather than intuition.

The inverse is automatic: **a metric-contract breach auto-demotes one level and writes an action item.** Correction rate spikes → the agent loses autonomy until a human reviews. This falls out of the Evaluator + action queue for free and is the single best argument for building them before turning autonomy up.

---

## Fixing the empty `audit/` package

### `audit/logger.py` — trace writer
Migration 026:

| Table | Grain | Key columns |
|-------|-------|-------------|
| `agent_runs` | one per request | `id`, `user_id`, `project_id`, `intent`, `persona`, `total_tokens_in/out/cached`, `total_cost_usd`, `latency_ms`, `outcome` |
| `agent_steps` | one per agent invocation | `run_id`, `agent_name`, `parent_step_id`, `model`, `tokens_in/out/cached`, `cost_usd`, `latency_ms`, `deterministic`, `react_iterations`, `autonomy_level`, `prompt_fragment_ids[]`, `prompt_version`, `input_hash`, `artifact_refs[]`, `status`, `error` |
| `agent_corrections` | one per human correction | `step_id`, `run_id`, `source`, `attributed_agent`, `severity`, `expected`, `actual`, `notes`, `created_by`, `confirmed` |
| `agent_action_items` | one per human-needed event | see Feedback section |
| `agent_autonomy` | one per agent | see Autonomy section |

API: `@traced("agent_name")` plus `start_run()` / `record_step()` / `finish_run()`, called by the runtime so an agent author cannot forget to instrument. `deterministic` is what makes the Crystallizer measurable; `react_iterations` is what makes loop cost visible.

### `audit/provenance.py` — reproducibility
Records **which corpus state produced an answer**: chunk IDs, document versions, `checksum_sha256`, `document_status` at answer time, prompt fragment versions. Documents get superseded — six months later "why did it say that?" is unanswerable without a snapshot. Also the evidence trail behind every action item.

### `audit/anomaly.py` — alerting
Statistics over traces, emitting action items: faithfulness below the 0.85 floor on a rolling window; cost or latency spike vs. an agent's own baseline; `cache_read_input_tokens` collapse; guard-trip rate spike; schema-validation failure rate rising; correction rate rising. Output goes to `agent_action_items` — logs don't get read.

**Import boundary unchanged:** `audit/ → db/, stdlib`. Anomaly detection is statistics, not an LLM.

---

## Feedback, action queue & superadmin dashboard

### Feedback capture — three granularities
| Level | Where | Volume | Value |
|-------|-------|--------|-------|
| **Answer** | thumbs up/down + text, all users | high | weak signal, good for trends |
| **Step** | expand a trace, thumbs-down one agent's step | low | precise, superadmin only |
| **Artifact** | correct a field — metadata proposal, bid line item, form field | medium | **highest** — a labeled example, not an opinion |

Artifact-level already has natural UI homes: the metadata review queue, the bid review, the form preview.

### Performance Review agent (#24)
Feedback is *data*, written deterministically — an LLM between your correction and the trace store is lossy, and the correction is training data. But attribution is genuinely hard: when an answer is wrong, was it bad chunks from Retrieval, hallucination from the Generator, a wrong persona fragment from the Router, or a mislabeled document that made the retrieval filter exclude the right source? The agent takes `(feedback, full run trace)` → structured correction with attributed agent, failure mode, evidence, confidence. Low confidence → human confirmation, never silent blame.

Consumers: Optimizer (proposes fixes), dashboard (correction rate), Crystallizer (confirmed-correct runs as rule candidates), autonomy engine (demotion trigger).

### `agent_action_items` — where "needs a human" goes
A table, not a view — a view is a pull mechanism and things rot in it.

Producers: Metadata Validator (unextractable date, content/metadata disagreement, supersession proposal) · Document Intake (source URL changed) · Freshness Watcher (upstream change) · Guardrail (injection attempt, missing disclaimer) · Anomaly detector (faithfulness/cost/cache trips) · Bid Evaluator (low-confidence extraction) · Form agents (unknown field, awaiting submit) · Optimizer/Crystallizer (PR ready).

Columns: `source_agent`, `kind`, `severity`, `blocking`, `entity_type`/`entity_id`, `evidence` (provenance ref), `proposed_action`, `status`, `resolved_by`, `resolved_at`, `resolution_note`.

**Blocking vs. non-blocking.** AGENTS.md forbids ingesting without full metadata, so a failing doc must not go live — but must not block the corpus. Reuse the existing `document_status` enum: failed docs sit in **`draft`** (already valid, `db/schema.sql:22`) with a blocking item.

**Resolution closes the loop** — resolving writes an `agent_corrections` row, so triage becomes training data for free.

**Notification, honestly scoped.** v1 is a dashboard badge plus a daily digest query. Firebase push is still an open README TODO and email is not wired — don't promise either.

### Superadmin dashboard
Auth already exists: `is_superadmin()` (`api/auth.py:138`), `require_admin(min_role="superadmin")` (`api/routes/admin.py:50`), migration 024, plan in `docs/cognito_groups_rbac.md`. Backend gating is reuse. The **frontend route guard is new**.

`/admin/agents`, superadmin only:
1. **Action queue** (landing) — open items by severity, filter by agent, inline resolve/dismiss with a note.
2. **Agent scorecard** — calls, cost, p50/p95 latency, tokens, deterministic-hit-rate, ReAct iterations, correction rate, contract scores vs. threshold.
3. **Cost** — spend by agent/model/day, budget trips, cache-read ratio, `filtered_out` waste.
4. **Trace explorer** — run DAG, per-step tokens and fragment versions, thumbs-down any step.
5. **Autonomy** — per-agent level slider, clamped to ceiling with reason shown; eligibility and auto-demotion history.
6. **Prompts** — fragment versions with eval deltas; Optimizer/Crystallizer PRs awaiting review.

---

## Corpus Metadata Validator (agent #13)

**Not a duplicate of `ingestion/verification.py`** — that verifies mechanics (bytes, chars, ≥80% chunk coverage, embeddings). It never asks whether metadata is *correct*. Integrate: extend `verification_stage` (`db/schema.sql:47`) with `'metadata'` and `verification_result` with `'needs_review'`; results land in the existing `ingestion_verifications` table.

**Deterministic first:**
1. **Enum + reference conformance** (no LLM) — against `db/schema.sql` enums and the `jurisdictions` table. Catches the 5 null docs.
2. **Required-field completeness** (no LLM) — AGENTS.md's six required fields. 27/27 fail on effective_date.
3. **Content-vs-metadata agreement** (LLM) — sample chunks **spread across the document**, propose values, flag disagreement **with the contradicting chunk** as evidence.
4. **Effective-date extraction** — codes state adoption dates in text; extract with a source-chunk citation. Unextractable → action item, not a silent null.
5. **Subject-tag regeneration** against a **closed controlled vocabulary**, whole-document sampled.
6. **Supersession candidate detection** — relevant to `city-of-dallas-ordiance-v1/v2/v3`, all three present (note the `ordiance` typo).

**Governance (AGENTS.md, non-negotiable):** writes nothing directly — all mutations through `ingestion/governance.py`; never auto-supersedes; never auto-updates on URL change; failing docs go to `draft` with a blocking action item.

**Backfill:** `scripts/backfill_document_metadata.py` does not depend on Phases 0–2 and can run in parallel if the schedule slips. ~$0.48 batched.

**Crystallizer target:** steps 1–2 are already deterministic; step 3's `doc_type` inference is the cleanest crystallization candidate in the system.

**Metadata source-of-truth redesign (owned by this phase).** Today the per-doc
sidecars in `documents/metadata/*.json` are a muddle: partly source, partly
derived. They mix hand-relevant fields (municipality, authority_level, doc_type,
subject_tags — which really originate in `documents/catalog.json`) with
per-ingest artifacts (ingested_at, review_due, checksums, verifications). They
are write-only (no runtime reader; the corpus lives in the DB), yet were tracked
in git, so every ingest produced churn. As of Phase 0 groundwork they are
**gitignored** (`catalog.json` + `registry.json` stay tracked). This phase must
settle the model properly:
- The DB is the corpus's source of truth; `catalog.json` is the source of the
  hand-curated fields; `registry.json` is the governance master.
- Decide whether the sidecars survive at all, or are replaced by the validator
  writing corrected metadata straight to the DB + `registry.json` via
  `governance.py`. If they survive as a local cache, keep them ignored.
- The validator's corrected `effective_date` / `doc_type` / `subject_tags` must
  land in the DB and the governance registry, **not** in an untracked sidecar
  that no one reads.

---

## Prompt Router (agent #2)

```
system_prompt = BASE (frozen, cached)
              + PERSONA fragment      (diy | hiring_contractor | contractor | research)
              + JURISDICTION fragment (dallas | plano | frisco | mckinney | fort-worth | tx | federal)
              + INTENT fragment       (compliance_lookup | how_to | bid_review | cost_estimate | form_fill)
              + EXPERIENCE modifier   (first_timer | experienced)
              + PROJECT NOTES         (bounded, sanitized, ≤200 tokens, last)
```

Selection is a **lookup, not an LLM call** — persona from `projects.persona`, jurisdiction from `rag/jurisdiction_resolver.py`, intent from the Manager. A model is called only when a fragment is missing, and that gap is logged as a Crystallizer input.

### Persona default — **`research`, not `diy`**
Persona can be absent: anonymous query, project created before kickoff completed, skipped wizard.

**Do not default to `diy`.** DIY framing tells someone they can do the work themselves — permit-pulling exemptions, step-by-step trade instructions. To a user actually hiring a contractor that's noise; to someone who shouldn't touch a service panel it's a safety and liability problem. A confident wrong DIY answer is the most costly default failure available.

Default to **`research`** — neutral, comparative, no action bias. Already in the enum and the kickoff prompt (`rag/generator.py:93`), so no new machinery. Clarification (#22) then asks once and persists to `projects.persona`.

**Intent can override persona for one request.** A `contractor` uploading a bid is likely reviewing a sub's — `bid_review` pulls the bid fragment without discarding the contractor register. Composition is additive: persona sets voice and depth, intent sets task behavior.

### Persona playbooks
**`diy`** — assume no trade background. Step-by-step, tool and material lists, tips, common mistakes, what pros do differently. Homeowner permit-pulling exemptions (Texas homestead rules vary by jurisdiction — cited, never assumed). Safety and inspection checkpoints. **Video demos** via Media Curator. Explicitly name what should *not* be DIY (gas, service panel, structural, licensed-trade-only work).

**`contractor`** — terse. Ordinance section and citation first. Submittal requirements, plan review timelines, inspection sequencing, fee schedules, licensing/bonding/insurance for that AHJ. No explanatory scaffolding.

**`hiring_contractor`** — layman's terms, every code term defined inline. Labor vs. materials split. What the permit means for *them* (who pulls it, who is liable, why unpermitted work surfaces at resale). Always ends with **questions to ask your contractor** and **red flags to watch for**. Bid uploads route to the Bid Evaluator.

**`research`** — neutral, comparative. Also the safe default.

### Media Curator (#17)
A model emitting a YouTube URL from memory produces dead links. Two sourced paths only: `web_search_20260209` with `allowed_domains: ["youtube.com"]` and citations, or a curated `media_refs` table (task → vetted URL → jurisdiction relevance → last-verified). Guardrail rejects any URL from neither.

---

## Bid Evaluator (agent #16)

**Input** — uploaded bid (PDF / image / spreadsheet). `ingestion/chunker.py` plus `messages.parse` against a `BidDocument` schema: contractor identity, license #, line items (description, qty, unit, unit price, labor/material split), allowances, exclusions, payment schedule, timeline, warranty, change-order terms, lien-waiver language, insurance certs.

**Three analyses, deterministic first:**
1. **Completeness** — checklist against a required-clauses table. Pure lookup. Crystallizer target from day one.
2. **Price reasonableness** — line items → Field Ontology → `commerce/product_resolver.py` for materials; labor from a seeded `labor_rate_benchmarks` table.
3. **Red flags** — rule table: missing license #, deposit >50% (Texas norm ~10–33%), no lien waiver, permit responsibility unassigned, verbal change orders, cash-only discount, no insurance cert, allowances hiding scope, timeline far off comparable scope. LLM only for novel flags.

**Output** — scored report + questions to ask + red flags + side-by-side comparison for 2+ bids.

**Labor-rate limitation — documented, not buried.** No free authoritative source; RSMeans is paid. v1 ships seeded public DFW ranges; every cost output labeled an estimate with its source; table designed for later swap-in of a licensed feed. Written into **README** ("Data Sources & Limitations", alongside existing SerpApi caveats), **`docs/agent_architecture.md`**, and the in-product disclaimer.

**Liability** — disclaimer modeled on `_AHJ_DISCLAIMER_TEXT` (`api/routes/query.py:44`): estimates only, not legal or financial advice, verify with the AHJ and a licensed professional. Guardrail enforces presence.

---

## Per-agent metric contracts (Evaluator)

| Agent | Metrics |
|-------|---------|
| Answer Generator | faithfulness (≥0.85), answer relevancy, citation density |
| Retrieval Strategist | context precision/recall, MRR@k, guard-trip rate |
| Corpus Metadata Validator | field precision/recall vs. hand-labeled docs; date-extraction accuracy; **false-flag rate** |
| Prompt Router | fragment-selection accuracy; per-version faithfulness delta; persona-appropriateness (LLM judge); **default-to-`research` rate** |
| Query Deconstructor | sub-question coverage, filter precision |
| Citation Verifier | claim-level precision/recall |
| Conflict Analyzer | detection precision/recall, false-alarm rate |
| Permit Strategy | permit-set F1 vs. `frontend/src/projectPermitRules.js` |
| Bid Evaluator | field accuracy, red-flag precision/recall, price MAPE where comparables exist |
| Media Curator | link liveness, relevance, **zero unsourced URLs** (hard gate) |
| PDF / Web Form | field accuracy, unknown-flag rate, human-edit rate |
| Manager | routing accuracy, plan length, replan rate, **ReAct iterations/run** |
| Performance Review | attribution accuracy vs. confirmed blame; % accepted without correction |
| **All** | tokens/call, cost/call, p50/p95 latency, deterministic-hit-rate, correction rate, **autonomy-level acceptance rate** |

---

## Token protocol

**1. Artifact store.** Agents pass `ArtifactRef(id, kind, summary, token_count, ttl)`, never raw text. Bounds ReAct blast radius.

**2. Model ladder.**

| Tier | Model | $/1M in/out | Use |
|------|-------|-------------|-----|
| Cheap | `claude-haiku-4-5` | $1 / $5 | classify, route, extract, enum checks (200K ctx) |
| Mid | `claude-sonnet-5` | $3 / $15 (intro $2/$10 thru 2026-08-31) | generation, citation verification, metadata inference, bids |
| Top | `claude-opus-4-8` | $5 / $25 | Manager on hard queries; Performance Review; Optimizer/Crystallizer |

`output_config={"effort": "low"}` on cheap-tier subagent calls.

**3. Prompt caching — two corrections.** Minimum cacheable prefix is **4096 tokens on Haiku 4.5 and Opus 4.8, 2048 on Sonnet-tier** — a ~500-token agent prompt **silently never caches** (`cache_creation_input_tokens: 0`, no error). Breakpoints go on large stable blocks (fragment library, form templates, ontology, tag vocabulary), not small prompts. Volatile content goes after the last breakpoint. Assert `cache_read_input_tokens > 0` in a test. 1h TTL for corpus/fragment blocks.

**4. Structured outputs — drop the planned `instructor` dependency.** Native: `client.messages.parse(output_format=PydanticModel)` → `response.parsed_output`. `pydantic>=2.7.0` already present. Zero new deps, guaranteed schema validity, no repair retries.

**5. Batch API** — 50% off for backfill, Evaluator, Performance Review, Optimizer, Crystallizer.

**6. Token counting** — `client.messages.count_tokens`, never `tiktoken` (undercounts Claude 15–20%).

**7. ReAct budgets** — `task_budget` (beta, min 20,000) on Manager and Web Navigator; `max_iterations` on every loop; context editing (`clear_tool_uses_20250919`) for the Navigator.

**8. Deterministic-first routing** — every agent checks its crystallized rule table before calling a model.

---

## Import boundaries (AGENTS.md)

Current: `rag/ → db/, audit/, stdlib`; `ingestion/ → db/, stdlib`; `audit/ → db/, stdlib`. The Manager must not import `commerce/`, `forms/`, or `bids/`.

**Tool registry with dependency injection** — `rag/agents/registry.py` defines `AgentSpec`; `api/main.py` registers commerce-, forms-, bids-, and ingestion-backed agents at startup.

AGENTS.md updates: add `forms/ → db/, stdlib`, `bids/ → db/, commerce/, stdlib`, `rag/agents/ → rag/, db/, audit/, stdlib`; allow `ingestion/ → rag/agent_runtime.py`; amend "no inline anthropic calls" to permit `rag/agent_runtime.py`. `rag/design_intent.py:147` already violates the current rule.

---

## Implementation phases

Priorities: (a) never lose the ability to attribute a quality regression, (b) accumulate meta-agent training data from the earliest moment, (c) put demo-visible capability before the deadline.

### Phase 0 — Trace store + the free cost fix
Migration 026 (all five tables) + three `audit/` modules + `@traced`. Retrofit `generate_answer` and `design_intent`. **Plus defect #2**: pass `result.passing_chunks` instead of `result.chunks` at `api/routes/query.py:423`.

**Why first.** Retrofitting telemetry across 26 agents costs far more than building it once, and the Optimizer, Crystallizer, and Performance Review all train on history — start at Phase 8 and they have zero data. The `filtered_out` fix rides along because it's one line and it's the only cost reduction available before there's anything to measure.

**Tradeoff accepted.** No user-visible output, at Week 10.

### Phase 1 — Agent runtime + registry + autonomy enforcement
`rag/agent_runtime.py` — the single Anthropic call site: `messages.parse`, tool_runner, caching, token accounting, model ladder, retries, automatic tracing, **and the autonomy-level check**. Plus `AgentSpec` + registry.

**Why here, and why autonomy this early.** Every agent written before the runtime is another independent call site. Autonomy enforcement lands here rather than with the dashboard because the *check* must be unbypassable from the first agent — the dashboard only edits a value the runtime already reads. Everything defaults to L0/L1 until the scorecard exists to justify more.

**Tradeoff accepted.** Second invisible phase.

### Phase 2 — Manager + artifact store + Budget Governor, zero behavior change
Port the existing chain behind the Manager. Same inputs, same outputs.

**Why deliberately capability-free.** The only phase where you can prove the abstraction didn't regress quality — `tests/test_query_answer_route.py` and RAGAs must be identical. Introduce the Manager *and* new agents together and a faithfulness drop is unattributable.

### Phase 3 — Metadata Validator + backfill + **dashboard v1**
Verification enum extensions, migration 028, `ingestion/metadata_agent.py`, backfill script, and the first dashboard slice: **action queue + metadata review**, gated on `is_superadmin()`.

**Why the validator this early.** `doc_type`, `authority_level`, `municipality`, `subject_tags` are retrieval filters and reranker inputs. Building the measurement layer on a corpus you know is wrong means measuring the wrong thing precisely.

**Why the dashboard here rather than late.** The validator's entire output is proposals needing review — without a queue UI it produces action items nobody can act on. And Phases 0–2 produce nothing visible; a fourth consecutive invisible phase at Week 10 was this plan's weakest point. Pulling the queue forward makes Phase 3 the first demo-able milestone *and* gives the validator its required review surface.

**Tradeoff accepted.** The dashboard ships in two passes, touching the same frontend route twice.

### Phase 4 — Prompt Router + fragment library + Media Curator
Migration 029. Author the persona playbooks, jurisdiction and intent fragments. Demote `custom_system_prompt` to bounded notes. Wire the `research` default + Clarification nudge. **Make `max_tokens` persona/intent-aware** (`generate_answer` hard-codes 1024 at `rag/generator.py:339`, which will truncate `diy` and `hiring_contractor` answers), and make `stop_reason == "max_tokens"` a Guardrail trip that files an action item.

**Why before the new answer agents.** (1) The Router changes every downstream agent's system prompt — build them first and you rewrite their prompts here anyway. (2) It fixes the cross-project cache defeat, paying for itself in tokens immediately. (3) Highest demo-value-per-token: one question as a DIYer, a contractor, and someone hiring a contractor returning three genuinely different answers is the most legible demonstration of "agents" to a non-technical audience.

**Tradeoff accepted.** The fragment library is hand-authored content, not code. It will take longer than its line count suggests and its quality caps the product's perceived quality.

### Phase 5 — Answer agents + Evaluator + Performance Review + feedback + dashboard v2 + **ontology core**
Query Deconstructor, Citation Verifier, Permit Strategy, `agent_eval.py`, `perf_review.py`, feedback UI, scorecard + trace explorer + autonomy controls. **Plus the Field Ontology core (items 1–3 below) only.**

**Why feedback here.** Performance Review attributes failure to an agent — with two agents there's nothing to attribute. It needs metric contracts to reason against.

**Why the ontology core lands here.** See the Phase 6 analysis: the vocabulary is cheap and has non-form consumers (Project Memory, Permit Strategy) that benefit immediately. Splitting it out de-risks Phase 6 and salvages value if 6–7 slip.

**This is the course cut line.** Phases 0–5 are the demo.

### Phase 6 — Bid Evaluator (+ ontology mappings)
Migration 030. Extraction, three analyses, comparison view, disclaimer, README limitations section.

**What the Field Ontology actually is** — seven parts, very different costs:

| # | Part | Effort | Notes |
|---|------|--------|-------|
| 1 | Canonical field vocabulary (~150–300 named facts: `parcel.legal_description`, `structure.occupancy_group`, `electrical.service_amps`, `contractor.license_number`, `work.valuation`) | **1–2 days** | Design exercise + seed migration |
| 2 | Type + validation per field (enum, currency, measurement-with-unit, license-number formats by trade/state) | **1 day** | Bounded |
| 3 | Source binding — which fact comes from `projects`, kickoff, room-scan metrics, GIS, profile, or "must ask" | **1 day** | Bounded |
| 4 | **Per-form mapping** (form fingerprint → field name/coords → canonical fact) | **linear in forms, indefinite** | The grind. Procedure and promotion criterion below. |
| 5 | Per-bid mapping (free-text line item → canonical work item) | **hard** | Bid text is unconstrained |
| 6 | Synonym/alias resolution ("sq ft"/"SF"/"square feet"; "GC"/"general contractor") | moderate | Grows with corpus |
| 7 | Unit normalization (room scan is metric, permits are imperial, bids mix) | 1 day | Bounded |

**The ontology core (1–3, plus 7) is not the hard part — the per-form mapping corpus (4) is.** That's why 1–3 move to Phase 5 and 4–6 accrete in Phases 6–7.

**Tradeoff accepted.** Labor-rate data is the weak link. Shipping a cost opinion on soft data is a real product risk; the mitigation is labeling, not precision.

### Phase 7 — PDF Form agent + the mapping corpus

Deterministic template caching per form fingerprint. No sessions, no credentials, no CAPTCHA, no irreversible filing.

#### Mapping a new form — the procedure

1. **Fingerprint** — hash of (sorted AcroForm field names + page count + normalized title text). Look up `form_templates`; an exact hit skips to step 7.
2. **Extract the field inventory.**
   - AcroForm PDF: field names, types, and page rects via `pypdf` / `pdfplumber`.
   - Flat or scanned: OCR + layout extraction → label text with bounding boxes, nearest-neighbor label-to-input pairing.
3. **Propose mappings** — for each form field, one `messages.parse` call over (field label, surrounding text, section heading, the ontology vocabulary) → `{canonical_key, confidence, rationale}`. Batch the whole form in one call; do not loop per field.
4. **Human review** in the dashboard — two-pane: form field left, proposed canonical key right, sorted by ascending confidence so the doubtful ones surface first. Confirm / correct / mark unmappable.
5. **Persist** — a `form_templates` row (fingerprint, jurisdiction, permit type, version) plus `field_mappings` rows. Versioned; a form revision creates a new template, never an in-place edit.
6. **Every correction writes an `agent_corrections` row** — artifact-level feedback, the highest-value kind, feeding the Optimizer for free.
7. **Add the form to the held-out eval set** and re-run the family's accuracy metric.

#### When is inference good enough? — measured, not guessed

Do not pick a number of examples. Maintain a labeled eval set and let it decide, **per form family (jurisdiction × permit type)** rather than globally. Forms cluster hard — a Dallas and a Plano building permit ask for nearly the same ~40 facts, so building permits may clear the bar at 6 examples while electrical is still at 60%.

This is the **graduated autonomy mechanism applied to one agent** — reuse it, don't build a parallel system:

| Stage | Criterion | Behavior |
|-------|-----------|----------|
| **L0 — manual** | family accuracy < 90% | Every field mapped by hand |
| **L1 — infer + confirm all** | ≥90% field accuracy on held-out forms, sustained over ≥5 consecutive new forms | Agent proposes the full map; human confirms every field |
| **L2 — infer + spot-check** | ≥97% over ≥20 forms in the family | Agent maps; human reviews only fields below a confidence floor |

Ceiling stays at L2 — a filled permit application always gets human eyes before it leaves.

Practical expectation for DFW: municipal permit forms are highly stereotyped, so **8–15 mapped forms per family** is a reasonable guess for reaching L1. But the eval promotes, not the guess, and the dashboard surfaces eligibility the same way it does for every other agent.

### Phase 8 — Optimizer, then Crystallizer
Propose-only, PR output, Batch API, budget-capped.

**Why here rather than last.** Functions of trace and correction volume — a Crystallizer run against fewer than ~100 traces per cluster produces overfit rules that look like insight and behave like bugs. Eight phases of tracing and three of feedback are enough. Critically, **this no longer sits behind the Web Form Navigator**, so the meta tier — the intellectual payoff of the whole design, and the part most legible as course work — is not hostage to the riskiest external dependency in the plan.

### Phase 9 — Web Form Navigator *(optional; droppable without stranding anything)*
Claude Agent SDK, behind a feature flag. Draft → approve → submit, `task_budget` capped, context editing on the loop, submit permanently clamped to L1.

**Why it is now its own phase — and last.** Splitting it from the PDF agent materially improves the tradeoff, because the two share almost nothing:

| | PDF Form (Phase 7) | Web Navigator (Phase 9) |
|---|---|---|
| Environment | Offline, a file | Live third-party portal |
| Failure modes | Bad OCR, unmapped field | Session expiry, CAPTCHA, DOM change, rate limiting |
| Credentials | None | Portal login required |
| Reversibility | Draft, fully reversible | **Irreversible government filing** |
| Cost per unit | ~cents | **$0.50–$2.00 per session** |
| Autonomy ceiling | L2 | **L1, permanently** |
| Caching | Template per fingerprint, high reuse | Macro replay, brittle across portal changes |

Bundled, the PDF agent is hostage to the Navigator's risk — one CAPTCHA problem and neither ships. Separated, PDF delivers most of the user value on a bounded, controllable surface, and the Navigator can slip indefinitely or be dropped entirely with nothing half-built left behind. **This is the answer to "does splitting make the tradeoff more amenable" — yes, because it lets the droppable thing actually be droppable instead of sitting in front of work you want.**

### Cost of deferring Phases 6–7

**What you lose:**
- **Product differentiation.** RAG Q&A is table stakes; "fill my permit" and "is this bid fair" are the reasons someone pays. Deferring means the demo shows intelligence but not utility.
- **The artifact-feedback flywheel.** Form templates and bid corrections are the highest-value training data — labeled examples, not opinions. Deferring delays the Optimizer's best input.
- **The ontology's real consumers.** Designing a shared vocabulary with zero live consumers risks designing it wrong. Mitigated by shipping the core in Phase 5 against Project Memory and Permit Strategy, which are real consumers.

**What you don't lose:**
- **Schedule realism.** The README timeline ends Aug 1. These phases were never going to fit — deferring names that, it doesn't cause it.
- **Requirements churn.** Permit forms and bid conventions don't move fast; a six-month delay doesn't invalidate the design.
- **Sunk work.** With the ontology core in Phase 5 and the Navigator split to Phase 9, nothing half-built is stranded.

---

## Files

**New**
- `rag/agent_runtime.py`
- `rag/agents/` — `registry.py`, `manager.py`, `prompt_router.py`, `budget.py`, `guardrail.py`, `deconstructor.py`, `retrieval.py`, `citation_verifier.py`, `permit_strategy.py`, `instructions.py`, `media.py`, `intake.py`, `freshness.py`, `memory.py`, `clarify.py`, `artifacts.py`, `autonomy.py`
- `rag/prompts/` — versioned fragment files
- `ingestion/metadata_agent.py`, `scripts/backfill_document_metadata.py`
- `bids/` — `evaluator.py`, `extract.py`, `red_flags.py`, `pricing.py`
- `forms/` — `ontology.py`, `pdf_agent.py`, `web_agent.py`
- `evaluation/agent_eval.py`, `evaluation/perf_review.py`, `evaluation/optimizer.py`, `evaluation/crystallizer.py`
- `api/routes/agents_admin.py` — dashboard, action queue, feedback, autonomy endpoints; `require_admin(min_role="superadmin")`
- `frontend/src/admin/` — `AgentDashboardPage.jsx`, `ActionQueue.jsx`, `AgentScorecard.jsx`, `TraceExplorer.jsx`, `AutonomyControls.jsx`, `FeedbackControls.jsx`
- `db/migrations/026_agent_traces.sql`, `028_metadata_validation.sql`, `029_prompt_fragments.sql`, `030_ontology_and_bids.sql`
  - Numbering note: `026` is a pre-existing duplicate (`026_agent_traces.sql` +
    `026_design_intent_usage_project_fk.sql`) — recorded, not renamed, both
    applied by name on prod + machine B. `027` is taken by
    `027_agent_action_item_dedupe.sql` (also applied). So Phase 3's metadata
    migration is **028**, and prompt fragments / ontology cascade to **029 / 030**.
- `docs/agent_architecture.md`
- Mirrored tests

**Modified**
- `audit/logger.py`, `audit/provenance.py`, `audit/anomaly.py` — 0 bytes today
- **`api/routes/query.py:423`** — `result.chunks` → `result.passing_chunks` (defect #2); later, hand-wired chain → Manager
- `db/schema.sql` — extend `verification_stage` (+`metadata`), `verification_result` (+`needs_review`)
- `ingestion/verification.py`, `ingestion/harvester.py`, `ingestion/governance.py`
- `api/routes/upload.py`, `api/routes/pull.py` — trigger validation post-ingest
- `rag/generator.py` — composed prompt from Router; **persona/intent-aware `max_tokens`** (replacing the hard-coded 1024 at line 339); register as agent; emit traces
- `rag/conflict_detector.py` — semantic tier C
- `rag/design_intent.py` — route through `agent_runtime`
- `rag/project_context.py` — persona/notes feed the Router
- `api/routes/projects.py` — kickoff writes fragment selections, not a blob
- `api/main.py` — agent registration; `agents_admin` router
- `frontend/src/context/AuthContext.jsx`, `frontend/src/main.jsx` — superadmin route guard (backend gate exists; frontend does not)
- `evaluation/langsmith_eval.py` — per-agent spans, fragment IDs
- **`README.md`** — agent roster; dashboard; **"Data Sources & Limitations"** (labor-rate seeding + SerpApi caveats); **cost model**; move finished TODOs to Completed per AGENTS.md
- `AGENTS.md`, `STATE.md`
- `pyproject.toml` — `pdfplumber`; `claude-agent-sdk` optional extra

---

## Verification

**Per phase**
```bash
py -m pytest tests/test_agent_runtime.py tests/test_agent_registry.py tests/test_audit_logger.py tests/test_autonomy.py -v
```

**Phase 0 — the free cost fix**
```bash
py -m pytest tests/test_query_answer_route.py -v
```
Must prove no `filtered_out=True` chunk reaches `_format_chunks_for_prompt`, and that measured input tokens drop.

**Phase 2 regression — behavior unchanged**
```bash
py -m pytest tests/test_query_answer_route.py tests/test_retriever.py tests/test_mini_rag.py -v
```

**RAG quality gate (AGENTS.md)**
```bash
py -m pytest tests/test_eval_guard.py -v && py -m evaluation.ragas_eval
```
Faithfulness ≥0.85, then `py -m evaluation.eval_guard` against baseline.

**Phase 3 — metadata + action queue**
```bash
py -m pytest tests/test_metadata_agent.py tests/test_verification.py tests/test_agents_admin_routes.py -v
py scripts/backfill_document_metadata.py --dry-run --report
```
`effective_date` populated or marked unextractable **with an action item** (from 27/27 null); zero null `doc_type`/`authority_level`; zero empty `subject_tags`; every proposal carries a source-chunk citation; failing docs in `draft`. Non-superadmins get 403 on every `/admin/agents` route.

**Phase 4 — persona routing**
```bash
py -m pytest tests/test_prompt_router.py tests/test_media_curator.py -v
```
Materially different answers across personas; `hiring_contractor` always emits questions-to-ask and red-flags; **missing persona resolves to `research`, never `diy`**; zero unsourced URLs; **no `diy` or `hiring_contractor` answer returns `stop_reason == "max_tokens"`** (the 1024 truncation defect).

**Parallelism**
```bash
py -m pytest tests/test_manager_parallel.py -v
```
Must prove: a 3-sub-question query issues 3 concurrent retrievals; all `tool_result` blocks return in a **single** user message (splitting them degrades future parallel tool use); wall-clock beats the sequential path; the connection pool is sized for `max_parallel_steps`.

**Phase 5 — feedback + autonomy**
```bash
py -m pytest tests/test_perf_review.py tests/test_feedback_routes.py tests/test_autonomy_ceilings.py -v
```
Thumbs-down attributed to the correct agent on a labeled set; resolving an action item writes a correction row; **an autonomy level above an agent's ceiling is rejected by the runtime, not just hidden in the UI**; a contract breach auto-demotes and files an action item.

**Cost proof**
```bash
py -m evaluation.agent_eval --report tokens
```
(a) Manager context ≤15% of total tokens; (b) `cache_read_input_tokens > 0` on the fragment library **including project-scoped queries** — the regression today's code fails; (c) measured cost/query vs. the ~$0.0067 baseline and against this plan's estimate; (d) deterministic-hit-rate and ReAct iterations per agent.

**End-to-end**
```bash
py -m evaluation.langsmith_eval --experiment-prefix agents-v1
```

**Manual**
- `/query` returns the same cited answer as before Phase 2.
- `/admin/agents` renders for superadmin, 403s for admin and member.
- Prod corpus smoke: `GET https://permits.scottsalhanick.com/api/documents` is not `[]`.
