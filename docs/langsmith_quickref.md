# LangSmith quick reference

One-screen cheat sheet. This is LangSmith (tracing/eval product), not the
LangChain framework — the query pipeline calls Anthropic directly.

Full docs: [session tracing](langsmith_session_tracing.md) ·
[prompt evaluation](langsmith_prompt_evaluation.md)

## Env vars (all three required to trace)

| Var | Value |
|---|---|
| `LANGCHAIN_TRACING_V2` | `true` |
| `LANGSMITH_API_KEY` | your key (prod: ECS task def, see `env_secrets_strategy.md`) |
| `LANGCHAIN_PROJECT` | optional, defaults to `permit-rag-app` |

Missing/unset → tracing silently no-ops, requests still work.

## Find a session's traces

The sidebar's `session_id` (sent as `X-Client-Session-Id`) is the same UUID
tagged on every LangSmith trace for that thread.

```python
from langsmith import Client
client = Client()
runs = client.list_runs(
    project_name="permit-rag-app",
    filter='eq(inputs.session_id, "the-uuid-here")',
)
```

Or in the UI: `permit-rag-app` project → filter runs by `inputs.session_id`.

## Change a prompt → measure it

```bash
# 1. baseline (before your change)
py -m evaluation.langsmith_eval --experiment-prefix baseline

# 2. edit PROMPT_VERSION (rag/generator.py) or a fragment's
#    <!-- version: N --> header, then:
py -m evaluation.langsmith_eval --experiment-prefix my-change

# 3. compare the two experiments in the LangSmith UI
```

## Update the eval dataset

Edit the JSON, then re-sync (the JSON is the source of truth — hand-edits in
the LangSmith UI get clobbered on next run):

```bash
py -m evaluation.langsmith_upsert_dataset
py -m evaluation.langsmith_upsert_dataset --file evaluation/langsmith_datasets/permit_rag_security_v1.json
```

## Two trace stores, not one

- **LangSmith** — request-level trace tree + UI/experiment comparison.
- **`agent_runs` (Postgres)** — per-agent-step cost/tokens/`prompt_fragment_ids`,
  powers the in-app Agent Dashboard and feedback loop. Not LangSmith.
