# Session 2026-07-26 — Phase 5 built to code-complete (machine A)

Machine A (repo, macOS, `.venv`). All model calls mocked; no DB/corpus ops here.

## Task (restated)
Close Phase 4 (done earlier in the day), then **start and finish Phase 5** — the
course cut line: answer agents (#5/#9/#11) + Evaluator #23 + Performance Review
#24 + feedback UI + dashboard v2 + Field Ontology core.

## Accomplished — all 8 Phase 5 components, 575 pytest green
Built in this order (each: module + mocked tests + register/verify):

1. **Feedback loop** — `033_answer_feedback.sql` (`answer_feedback`: run_id FK,
   user_id, rating up|down, comment, `UNIQUE(run_id,user_id)`); `db.upsert_answer_feedback`
   + `answer_feedback_counts`; `AnswerResponse.run_id` (both paths, via
   `_current_run_id()` off the `@traced_run` ctx); `FeedbackRequest`/`FeedbackResponse`;
   `POST /query/feedback` (404 on unknown run); QueryPage 👍/👎 + comment;
   `submitAnswerFeedback` in api.js. `tests/test_feedback_route.py` (5).
2. **Performance Review #24** — `evaluation/perf_review.py`: `(down-vote + trace)`
   → attributed agent. Deterministic-first (errored step / abstain = $0), else one
   `Tier.TOP` call; writes **unconfirmed** `agent_corrections`, no attribution below
   `CONFIDENCE_FLOOR=0.6`; hallucinated agent names clamped to None. Batch driver
   `scripts/review_feedback.py`; `db.list_downvotes_without_review`.
   `tests/test_perf_review.py` (7).
3. **Evaluator #23** — `evaluation/agent_eval.py`: per-agent metric contracts over
   scorecard + correction rate + latest RAGAs faithfulness; breach → action item +
   auto-demote one autonomy level (`--apply`). `scripts/run_agent_eval.py`.
   `tests/test_agent_eval.py` (6).
4. **Citation Verifier #9** — `rag/agents/citation_verifier.py`: deterministic
   token-span match first, one batched entailment call on leftovers; missing cited
   chunk = unsupported; flags uncited claims. Registered. `tests/test_citation_verifier.py` (6).
5. **Query Deconstructor #5** — `rag/agents/deconstructor.py`: compound →
   sub-questions + per-sub filters; deterministic gate for simple queries.
   Registered. `tests/test_deconstructor.py` (6).
6. **Permit Strategy #11** — `rag/agents/permit_strategy.py`: permit set (mirrors
   `frontend/src/projectPermitRules.js` → F1=1.0) + pull-order sequencing + fee
   estimate; only the note is a call. Registered. `tests/test_permit_strategy.py` (6).
7. **Field Ontology core (1-3)** — `forms/ontology.py` (new `forms/` package;
   AGENTS.md import boundary `forms/ → db/, stdlib` added): canonical vocabulary +
   per-field type/validation + source binding. Git-tracked module, no migration.
   `tests/test_ontology.py` (8).
8. **Dashboard v2** — `agents_admin.py` routes `/scorecard`, `/autonomy` (+set,
   409 over ceiling), `/runs/{id}/trace`, `/feedback-summary`, `/corrections`
   (+`/confirm`); `db.list_agent_corrections` + `confirm_agent_correction`;
   frontend `AgentScorecard` / `CorrectionQueue` / `AutonomyPanel` tabs on
   `AgentDashboardPage`. `tests/test_dashboard_v2_routes.py` (8).

Also this session: applied the Phase-3 metadata backfill `--apply` on **machine B
local** (028 applied, `needs_review` items filed; dashboard approvals pending) —
recorded in STATE's migration table.

## Verification (machine A)
- `py -m pytest tests/ -q` → **575 passed** (was 474 at Phase 4 close; +101).
- All new/changed files **ruff-clean** (the ~105 tree-wide hits are pre-existing:
  ragas_eval, older tests, the two db/client E402s — none introduced here).
- `frontend/ npm run build` clean.

## Key decisions (also in STATE decisions log)
- **Feedback is its own table**, not `agent_corrections` — a 👍 is not a correction;
  a 👎 is what Perf Review reads to *write* the attributed correction.
- **Perf Review + Evaluator are batch-triggered** (`scripts/`), never on the query
  hot path — `api/` may not import `evaluation/`, and the arch budgets them batched.
- **Perf Review never silent-blames**: always unconfirmed; below the confidence
  floor it leaves `attributed_agent` empty for a human. Model may only blame a
  fixed known-agent roster; a hallucinated name clamps to None.
- **Ontology core is a git-tracked module, not a migration** (like the Phase-4
  fragment library) — vocabulary changes with a code deploy; the DB tables arrive
  with the Phase-6 per-form mapping corpus.
- **Migration 033 = Phase 5**; Phase-6 ontology/bids cascades to **034** (the
  deployed 032's "cascades to 033" comment is stale — can't edit a deployed file).

## NOT done — the Phase 5 tail (next session)
- **Deploy:** apply `033_answer_feedback.sql` by hand (machine B → prod; confirm
  target — `.env` overrides `.env.local`), then commit + GHA. Migration 033 pending
  on ALL DBs.
- **Wire #5/#9/#11 into `manager.py`'s live query path** — they are built +
  registered + unit-tested but not yet in the request flow (Deconstructor →
  retrieval fan-out; Citation Verifier → post-gen on the response; Permit Strategy
  → a project surface). Regression-sensitive: re-run `test_query_answer_route` +
  RAGAs after.
- **Run the batch eval loops on machine B** + record the multi-sample RAGAs
  baseline (punch #3); then repoint `eval_guard` off `ragas_20260531`.

## Commit message (this session)
```
feat(phase5): answer agents (#5/#9/#11) + Evaluator #23 + Performance Review #24 + feedback loop (migration 033) + dashboard v2 + Field Ontology core — code-complete, 575 pytest green
```

## Prompt for next session
> Read STATE.md, the latest `journals/session_*.md`, AGENTS.md, and
> `docs/agent_architecture.md` before touching anything. Restate the current task
> (AGENTS.md pre-session protocol).
>
> **Phase 5 is code-complete on machine A (575 pytest green) but NOT deployed and
> the answer agents are not yet wired into the live query path.** Finish the tail:
> 1. **Deploy the feedback loop + dashboard v2.** Confirm the DB target, then
>    `py scripts/apply_migration.py db/migrations/033_answer_feedback.sql` (machine
>    B, then prod RDS — 033 is pending everywhere). Commit + GHA (touches
>    `api/`+`frontend/`). Smoke: answer a query → 👍/👎 → row in `answer_feedback`;
>    `/admin/agents` shows Scorecard / Corrections / Autonomy.
> 2. **Wire the three answer agents into `rag/agents/manager.py`** (they are
>    registered + unit-tested only): Query Deconstructor → one retrieval per
>    sub-question then merge; Citation Verifier → post-generation over the answer +
>    chunks (∥ conflict analyzer), surface unsupported claims; Permit Strategy → a
>    project-context surface. This is regression-sensitive — keep
>    `test_query_answer_route` green and re-run RAGAs (`--no-answer-cache`) on
>    machine B after.
> 3. **Run the eval loops on machine B:** `scripts/review_feedback.py` (Perf
>    Review over down-votes) + `scripts/run_agent_eval.py` (Evaluator), and record
>    the **multi-sample live RAGAs baseline** (run 3+, average out q6's ±0.15),
>    then repoint `eval_guard`'s default baseline off `ragas_20260531`.
>
> Details + the full component list are in STATE.md ("Phase 5 CODE-COMPLETE" banner)
> and `journals/session_20260726_phase5.md`.
