# LangSmith: finding evaluation scores in the browser

This is the missing piece between the other three LangSmith docs: how to
actually go *look* at evaluator scores in the web UI, not the API. For live
per-query tracing, see [`langsmith_session_tracing.md`](langsmith_session_tracing.md).
For running the offline harness itself, see
[`langsmith_prompt_evaluation.md`](langsmith_prompt_evaluation.md). One-screen
cheat sheet: [`langsmith_quickref.md`](langsmith_quickref.md).

## Two different sections of the UI — don't confuse them

LangSmith has two separate top-level areas, and eval scores live in the one
people don't think to check first:

- **Tracing / Projects** (`permit-rag-app`) — every live `/query/answer`
  request. This is what `langsmith_session_tracing.md` covers. No evaluator
  scores here; it's raw request traces.
- **Datasets & Experiments** — this is where `evaluation/langsmith_eval.py`'s
  output lives. Each dataset (`permit_rag_eval_v1`, `permit_rag_security_v1`)
  has its own page; every `py -m evaluation.langsmith_eval` run adds one
  **experiment** row underneath it, scored by whichever evaluators ran
  (`ALL_EVALUATORS` in that file).

In the left sidebar: **Datasets & Experiments**, not **Tracing Projects**.

## Finding a dataset's experiments

Direct links for this workspace (org id is fixed, dataset/experiment ids
shown are examples — yours will differ once you run a fresh experiment):

- `permit_rag_eval_v1` dataset page:
  `https://smith.langchain.com/o/60530d91-d225-4cc8-9b7b-a330b6592baa/datasets/d2b90f3c-17a4-41e3-b894-f4c036ee86a4`
- `permit_rag_security_v1` dataset page — same pattern, find its id with
  `client.read_dataset(dataset_name="permit_rag_security_v1").id` (see
  `langsmith_quickref.md`) or just navigate via the sidebar list.

Generic path if a link goes stale: **Datasets & Experiments** (sidebar) →
click the dataset name → **Experiments** tab. Rows are sorted by run date,
newest first.

## Reading the scores

Each experiment row shows one column per evaluator key from `ALL_EVALUATORS`:
`jurisdiction_correct`, `citation_precision`, `citation_recall`,
`abstention_correct`, `project_isolation`, `hallucination_judge`,
`cost_and_latency`. The cell shows the aggregate (mean for continuous scores,
pass-rate for 0/1 ones) across every example in that dataset. Click a column
header to sort experiments by that metric.

Click into an experiment row to see **per-example** results — one row per
dataset example, with its own score per evaluator and a link to the full
trace (retrieval → guardrail → generation → each evaluator's reasoning,
including the `hallucination_judge`'s judge-model output).

**Current state, checked live while writing this (2026-08-04):** exactly one
experiment has ever run against `permit_rag_eval_v1`
(`baseline-v1-6c59e06b`, 2026-07-22) and it has **zero recorded scores** — the
`feedback_stats` are empty, meaning no evaluator actually scored anything on
that run. `permit_rag_security_v1` has never been run at all. So opening
either dataset's Experiments tab today will look mostly empty — that's
accurate, not a UI problem. The first time this becomes genuinely useful is
after a fresh `py -m evaluation.langsmith_eval` run with the current,
evaluator-equipped code.

## Comparing two experiments

Select two or more experiment rows (checkboxes on the left of each row) →
**Compare**. This is the view described in `langsmith_prompt_evaluation.md`'s
"worked example" — same dataset, same evaluators, different `prompt_version`/
`library_version` tag, side by side. Per-example deltas are color-coded;
aggregate deltas show at the top of each evaluator column.

## Where `agent_eval.py`'s advisory metrics come from

`evaluation/agent_eval.py`'s `_latest_langsmith_metrics()` reads exactly what
this page describes — the latest *version-matched* experiment's
`feedback_stats` — via the API, not the browser. If a number in
`run_agent_eval.py`'s report output looks wrong, the browser view above is
the fastest way to sanity-check it against the same experiment by eye.
