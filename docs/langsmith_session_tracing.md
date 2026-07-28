# LangSmith: session tracing

A note on naming, since this gets confused a lot: this repo does **not** run
its query pipeline through the LangChain framework (chains/agents). Generation
is a direct Anthropic SDK call (`rag/generator.py`). What *is* wired up is
**LangSmith** — a separate (if related) product used purely for tracing and
evaluation. This doc, and its companion
[`langsmith_prompt_evaluation.md`](langsmith_prompt_evaluation.md), describe
LangSmith only.

For prompt-version tagging and the offline evaluation harness, see
[`langsmith_prompt_evaluation.md`](langsmith_prompt_evaluation.md). For a
one-screen cheat sheet, see [`langsmith_quickref.md`](langsmith_quickref.md).

## Enabling tracing

Tracing is off unless both of these are set:

| Env var | Purpose |
|---|---|
| `LANGCHAIN_TRACING_V2` | Must be `1`/`true`/`yes`/`on` |
| `LANGSMITH_API_KEY` | LangSmith API key |
| `LANGCHAIN_PROJECT` | Optional; defaults to `permit-rag-app` |

Checked at request time by `_langsmith_enabled()` in
[`api/routes/query.py:131`](../api/routes/query.py). If the key is missing or
the `langsmith` package isn't installed, tracing silently no-ops — it never
breaks a request (every trace call is wrapped in try/except that just logs a
warning). In prod, `LANGSMITH_API_KEY` lives in the ECS task definition; see
[`env_secrets_strategy.md`](env_secrets_strategy.md).

## How a request becomes a trace

`query_answer` (`api/routes/query.py`) opens one root span per request —
`api_query_answer` — via `_start_trace`/`_end_trace`, which wrap
`langsmith.run_trees.RunTree` directly (not LangChain's callback/tracer
system — this is a manual integration). Its inputs carry `session_id`,
`request_id`, `query`, `municipality`, `top_k`; its metadata carries
`prompt_version`, `user_id`, `user_role`, `project_id`.

The Manager's retrieval/generation stages become child spans
(`api_retrieval`, `api_generation`) through `_LangSmithObserver`
(`api/routes/query.py:186`) — it exists specifically so `rag/agents/` never
has to import LangSmith itself (import-boundary rule in `AGENTS.md`); the
route translates the Manager's plain stage-started/finished callbacks into
spans. The `api_generation` span additionally tags `prompt_version` in its
metadata, so a live trace always tells you which prompt version answered it
(more on that in [`langsmith_prompt_evaluation.md`](langsmith_prompt_evaluation.md)).

## Session grouping — same ID as the query-history threads

The `session_id` your browser generates for the sidebar's session grouping
(see `frontend/src/QueryPage.jsx`'s `makeSessionId()`, sent as
`X-Client-Session-Id`) is the **exact same UUID** attached to the LangSmith
root span's inputs. There's no separate "LangSmith session" concept to wire
up — filtering LangSmith by that `session_id` gives you every turn of one
sidebar thread as a single, chronological set of traces.

**In the LangSmith UI:** open the `permit-rag-app` project, filter runs by
`session_id` in the inputs (or search `metadata.session_id` /
`inputs.session_id` depending on UI version) to see one thread end to end —
each turn's retrieval, generation, prompt version, cost, and latency.

**Via the API:**
```python
from langsmith import Client

client = Client()
runs = client.list_runs(
    project_name="permit-rag-app",
    filter='eq(inputs.session_id, "the-uuid-here")',
)
for run in runs:
    print(run.name, run.start_time, run.extra.get("metadata", {}).get("prompt_version"))
```

## The other trace store: `agent_runs`

There's a second, separate trace store: the `agent_runs` Postgres table
(`audit/logger.py`'s `traced_run`/`record_step`/`annotate_run`), which records
per-agent-step token counts, `cost_usd`, and `prompt_fragment_ids` — that's
what powers the in-app Agent Dashboard/Scorecard and the answer-feedback loop
(`run_id`). LangSmith gives you the request-level trace tree and the
UI/experiment tooling; `agent_runs` gives you fragment-level cost/version
attribution queryable straight from Postgres. They're complementary, not
duplicates — see [`agent_architecture.md`](agent_architecture.md) for the
`agent_runs` side.
