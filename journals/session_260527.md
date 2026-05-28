# Session: 2026-05-27

## Type

Fix — evaluation/ RAGAs relevancy + faithfulness reliability + eval answer caching.

## Goal

Fix Answer Relevancy scoring failure caused by the custom embeddings wrapper,
stabilize faithfulness scoring behavior, and reduce eval token spend via
generation answer caching.

---

## Completed

### Patched evaluation/ragas_eval.py

- Replaced subclass-based `NomicEmbeddings(HuggingfaceEmbeddings)` adapter
  with composition via `LangchainEmbeddingsWrapper(HuggingFaceEmbeddings)`.
- Added import compatibility fallback:
  - preferred: `langchain_huggingface.HuggingFaceEmbeddings`
  - fallback: `langchain_community.embeddings.HuggingFaceEmbeddings`
- Moved embeddings initialization out of per-sample path:
  - created once in `run_evaluation()`
  - threaded into `evaluate_query()` and `_score_sample()`
- Kept metric-level fault tolerance and added explicit warning when embeddings
  initialization fails.
- Increased evaluator token budget and made it env-configurable via
  `RAGAS_EVAL_MAX_TOKENS`.
- Added faithfulness retry handling for `LLMDidNotFinishException` via
  `RAGAS_FAITH_RETRIES`.
- Added generation-only answer caching with strict invalidation key:
  - cache storage: JSON file (default `evaluation/cache/answers.json`)
  - strict key fields: query, municipality, top_k, model, prompt version, and
    retrieved chunk fingerprint (hash)
  - env knobs: `RAGAS_ANSWER_CACHE_ENABLED`, `RAGAS_ANSWER_CACHE_PATH`,
    `RAGAS_ANSWER_CACHE_PROMPT_VERSION`
  - observability: per-query `Answer cache: hit/miss` and summary hit/miss totals
- Added provider-capability-gated evaluator path:
  - uses Anthropic-native evaluator adapter when
    `LLM_PROVIDER=anthropic` and prompt caching is enabled
  - falls back to existing LangChain evaluator wrapper otherwise

### Updated pyproject.toml (eval extras)

- Added `langchain-huggingface>=0.1.0` to `[project.optional-dependencies].eval`
  to align with the preferred import path used in `ragas_eval.py`.

### Validation outcomes

- Smoke run (`--query 0`) now prints numeric relevancy (no longer `—`):
  - Faithfulness: `0.778`
  - Relevancy: `0.000`
  - Context Precision: `0.200`
- Partial full-run evidence confirms relevancy is functioning across queries
  (observed values include `0.000` and `0.996`).
- New/remaining issue surfaced during full run:
  - Faithfulness intermittently fails with
    `LLMDidNotFinishException: The LLM generation was not completed. Please increase the max_tokens and try again.`
- Cache validation with identical query (`--query 0`) confirms cost-saving behavior:
  - Run 1: `Answer cache: miss` and summary `0 hit(s), 1 miss(es)`
  - Run 2: `Answer cache: hit` and summary `1 hit(s), 0 miss(es)`
  - Metrics remained unchanged between runs for the cached answer path.
- Prompt-caching instrumentation validation:
  - evaluator logs now emit cache usage counters
    (`cache create/read=<x>/<y>`) per call.
  - sampled run showed `cache create/read=0/0` repeatedly, so explicit prompt
    caching is wired but not yet producing cache-token savings on those calls.

### Patched rag/generator.py

- Added provider-capability-gated Anthropic prompt caching support:
  - `ANTHROPIC_PROMPT_CACHE_ENABLED`
  - `ANTHROPIC_PROMPT_CACHE_TTL` (`5m` or `1h`)
- Uses explicit breakpoint on stable system prompt block when enabled.
- Logs Anthropic cache token usage when returned by API.

### Added rag/llm_provider.py

- Added provider abstraction utilities:
  - `get_llm_provider()`
  - `get_provider_capabilities()`
- Current capabilities include `supports_prompt_caching`, enabling clean no-op
  behavior for non-Anthropic providers.

### Added evaluation/anthropic_eval_llm.py

- Added Anthropic-native RAGAS evaluator wrapper with explicit prompt-cache
  breakpoint on static evaluator system prompt.
- Exposes usage logging for cache creation/read tokens and maps stop reasons to
  RAGAS completion checks.

### Updated STATE.md

- RAGAs section updated from "last run: never" to current smoke/partial-full status.
- Module status updated to `eval 🔶`.
- Next task now explicitly targets faithfulness stabilization (`max_tokens`).
- Added decisions capturing the embeddings wrapper architecture and dependency path.
- Added answer-cache strategy + miss→hit validation evidence.

---

## Files changed

- evaluation/ragas_eval.py
- pyproject.toml
- .env.example
- rag/generator.py
- rag/llm_provider.py
- evaluation/anthropic_eval_llm.py
- STATE.md
- journals/session_260527.md

## Files NOT changed

- rag/retriever.py, rag/pipeline.py
- api/routes/* (no endpoint work in this session)
- db/* (no schema/client changes in this session)

---

## Decisions made

- Use composition (`LangchainEmbeddingsWrapper`) instead of subclassing
  `ragas.embeddings.HuggingfaceEmbeddings` to avoid pydantic validation issues.
- Standardize on `langchain-huggingface` as primary embedding adapter import,
  with `langchain_community` fallback for compatibility.
- Use generation-only answer caching for eval with strict key invalidation
  (no metric caching in v1) to reduce Anthropic spend while preserving metric freshness.
- Treat prompt caching as a provider capability (not core dependency) so
  non-Anthropic production paths remain first-class via fallback/no-op behavior.

---

## Next session should

1. Diagnose why evaluator prompt cache usage remains `cache create/read=0/0` and adjust breakpoint placement/prefix stability.
2. Tune cost/performance defaults (`RAGAS_EVAL_MAX_TOKENS`, `RAGAS_FAITH_RETRIES`) for lowest stable spend.
3. Re-run full 7-query RAGAs with both answer cache and prompt-cache instrumentation enabled.

## Prompt for next session

Read STATE.md and journals/session_260527.md. Keep generation answer caching enabled
for routine eval runs, then investigate Anthropic prompt caching effectiveness:
evaluator logs currently show cache create/read tokens as 0/0. Verify breakpoint
placement and prompt-prefix stability, then tune `RAGAS_EVAL_MAX_TOKENS` and
`RAGAS_FAITH_RETRIES` to minimize spend while keeping faithfulness stable. Run a
full 7-query RAGAs pass and capture averages plus answer-cache and prompt-cache
usage totals.

## Git commit message

feat(eval): add provider-gated Anthropic prompt caching path (generator + evaluator), preserve non-Anthropic fallback behavior, and document cache usage validation alongside strict-key answer caching
