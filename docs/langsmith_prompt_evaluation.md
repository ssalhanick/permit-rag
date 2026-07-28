# LangSmith: prompt monitoring & optimization

This assumes LangSmith tracing is already enabled — see
[`langsmith_session_tracing.md`](langsmith_session_tracing.md) for the env
vars and how a request becomes a trace. For a one-screen cheat sheet, see
[`langsmith_quickref.md`](langsmith_quickref.md).

There are two distinct things "prompt optimization" means here — live
production visibility, and offline experiment comparison.

## 1. Live traffic, tagged by prompt version

Every `api_generation` span (and the root span) carries `prompt_version`
(`rag/generator.py`'s `PROMPT_VERSION`, currently `"v1"`). When a request goes
through the persona/fragment router (`rag/agents/prompt_router.py::route`),
the routed system prompt's `fragment_ids` and `library_version` are also
available on that call's outputs. In practice: bump `PROMPT_VERSION` (or a
fragment's `<!-- version: N -->` header in `rag/prompts/fragments/*.md`) when
you change a prompt, and every trace from that point on is taggable/filterable
by the new version — so you can compare latency, cost, and (via the
evaluators below) quality before vs. after in the LangSmith UI.

## 2. Offline evaluation — comparing prompt versions on a fixed dataset

`evaluation/langsmith_eval.py` is the harness for this. It re-runs the same
pipeline (`retrieve_with_project` → guardrail → `detect_conflicts` →
`generate_answer`) outside of FastAPI, against a checked-in dataset, and
uploads the results as a named **experiment** in LangSmith:

```bash
# Run the default dataset (permit_rag_eval_v1)
py -m evaluation.langsmith_eval

# Or a specific dataset / experiment name
py -m evaluation.langsmith_eval --dataset permit_rag_security_v1 --experiment-prefix persona-v2-test
```

Each example gets scored by `ALL_EVALUATORS`
(`evaluation/langsmith_eval.py:333`):

| Evaluator | What it checks |
|---|---|
| `jurisdiction_correct` | Resolved municipality matches expected |
| `citation_precision` / `citation_recall` | Cited chunks vs. the expected set |
| `abstention_correct` | Abstained exactly when it should have |
| `project_isolation_regression` | No cross-project chunk leakage |
| `hallucination_judge` | Claude-Haiku groundedness judge (skipped when abstained) |
| `cost_and_latency` | `cost_usd` + total latency (non-pass/fail, just a number) |

Every experiment carries `metadata={"prompt_version": PROMPT_VERSION, ...}`,
so two experiment runs — before and after a prompt change — show up
side by side in LangSmith's comparison view, scored on the exact same
evaluator set.

**Worked example — measuring a prompt change:**
1. Run the harness once on `main`/current prompt to get a baseline experiment.
2. Change the prompt (bump `PROMPT_VERSION`, or edit a fragment + its
   `<!-- version: N -->` header).
3. Run the harness again with a descriptive `--experiment-prefix`.
4. Open both experiments in the LangSmith UI's comparison view — same
   dataset, same evaluators, different prompt — to see per-example and
   aggregate deltas (pass rate, citation precision/recall, cost, latency).

## Managing the dataset itself

The dataset is a checked-in JSON fixture
(`evaluation/langsmith_datasets/permit_rag_eval_v1.json`,
`permit_rag_security_v1.json`), **not** the LangSmith UI. Editing examples
directly in LangSmith will be silently overwritten on the next sync:

```bash
py -m evaluation.langsmith_upsert_dataset
py -m evaluation.langsmith_upsert_dataset --file evaluation/langsmith_datasets/permit_rag_security_v1.json
```

Add/edit test cases in the JSON file, run the upsert, then run
`langsmith_eval` against it.
