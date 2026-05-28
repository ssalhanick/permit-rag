"""
evaluation/ragas_eval.py — RAGAs evaluation harness for permit_rag
===================================================================
Runs the 7 predefined test queries through retrieve() + generate_answer(),
scores each with RAGAs metrics (faithfulness, relevancy, context precision),
and outputs a summary table.

Import boundary: evaluation/ → rag/, db/, standard library only (AGENTS.md).

Requires:
    - ANTHROPIC_API_KEY in .env  (for both generation and RAGAs evaluation)
    - DATABASE_URL in .env       (for retrieval)
    - Docker Postgres running    (pgvector)

CLI usage:
    py -m evaluation.ragas_eval                    # full eval (7 queries)
    py -m evaluation.ragas_eval --retrieval-only   # skip generation, score context only
    py -m evaluation.ragas_eval --query 0 2 4      # run specific queries by index
"""

from __future__ import annotations

# ── Compatibility shim (must come before any ragas import) ────
import evaluation._ragas_shim  # noqa: F401 — patches langchain import paths

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ragas import SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.exceptions import LLMDidNotFinishException
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerRelevancy,
    Faithfulness,
    LLMContextPrecisionWithoutReference,
)

from rag.retriever import RetrievalResult, retrieve
from rag.llm_provider import get_provider_capabilities

log = logging.getLogger(__name__)
ANSWER_CACHE_DEFAULT_PATH = "evaluation/cache/answers.json"
ANSWER_CACHE_PROMPT_VERSION = "v1"


# ── Test queries (mirrors rag/pipeline.py TEST_QUERIES) ──────

TEST_QUERIES: list[dict[str, Any]] = [
    {
        "query": "What are the setback requirements for a residential fence in Dallas?",
        "municipality": "dallas",
        "top_k": 10,
        "notes": "Expects Dallas ordinance chunks about fences/setbacks",
    },
    {
        "query": "Do I need a permit for electrical work in Texas?",
        "municipality": None,
        "top_k": 10,
        "notes": "Expects texas-contractor-licensing-electrical chunks",
    },
    {
        "query": "What are the ADA accessibility requirements for commercial buildings?",
        "municipality": None,
        "top_k": 10,
        "notes": "Expects ada-design-standards and texas-accessibility-standards",
    },
    {
        "query": "What is the stormwater management plan requirement for construction sites?",
        "municipality": None,
        "top_k": 10,
        "notes": "Expects epa-stormwater-construction chunks",
    },
    {
        "query": "What are the building permit requirements in Plano?",
        "municipality": "plano",
        "top_k": 10,
        "notes": "Expects plano-building-permit-info chunks",
    },
    {
        "query": "What are the fire sprinkler requirements for new construction in Dallas?",
        "municipality": "dallas",
        "top_k": 10,
        "notes": "Expects Dallas ordinance chunks about fire/sprinkler codes",
    },
    {
        "query": "What is the maximum building height allowed in a residential zone?",
        "municipality": "dallas",
        "top_k": 10,
        "notes": "Expects Dallas zoning/ordinance chunks about height limits",
    },
]


# ── Result container ─────────────────────────────────────────


@dataclass
class EvalResult:
    """Scores for a single query evaluation."""

    query: str
    municipality: Optional[str]
    num_chunks: int
    top_similarity: float
    faithfulness: Optional[float] = None
    relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    answer_preview: str = ""
    latency_retrieval_ms: int = 0
    latency_generation_ms: int = 0
    latency_scoring_ms: int = 0
    answer_cache_hit: Optional[bool] = None
    error: Optional[str] = None


@dataclass
class CacheStats:
    """Cache hit/miss counters for the current eval run."""

    hits: int = 0
    misses: int = 0


# ── LLM + Embeddings factory ─────────────────────────────────


def _get_evaluator_llm() -> Any:
    """Create evaluator LLM wrapper for RAGAs scoring."""
    from langchain_anthropic import ChatAnthropic

    model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
    max_tokens = int(os.environ.get("RAGAS_EVAL_MAX_TOKENS", "4096"))
    capabilities = get_provider_capabilities()
    cache_requested = _env_bool("ANTHROPIC_PROMPT_CACHE_ENABLED", False)
    if capabilities.supports_prompt_caching and cache_requested:
        from evaluation.anthropic_eval_llm import AnthropicCachedEvalLLM

        cache_ttl = os.environ.get("ANTHROPIC_PROMPT_CACHE_TTL", "5m")
        return AnthropicCachedEvalLLM(
            model=model,
            max_tokens=max_tokens,
            cache_enabled=True,
            cache_ttl=cache_ttl,
        )
    if cache_requested and not capabilities.supports_prompt_caching:
        log.info(
            "Evaluator prompt caching requested but provider '%s' does not support it.",
            capabilities.provider,
        )
    llm = ChatAnthropic(
        model=model,
        temperature=0.0,
        max_tokens=max_tokens,
    )
    return LangchainLLMWrapper(llm)


def _get_evaluator_embeddings() -> Any:
    """Create wrapped embeddings instance for RAGAs AnswerRelevancy."""
    model_name = os.environ.get(
        "EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5"
    )
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ImportError:
        from langchain_community.embeddings import HuggingFaceEmbeddings

    lc_embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"trust_remote_code": True},
        encode_kwargs={"normalize_embeddings": True},
    )
    return LangchainEmbeddingsWrapper(lc_embeddings)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _cache_path() -> Path:
    """Resolve answer cache file path from environment."""
    raw = os.environ.get("RAGAS_ANSWER_CACHE_PATH", ANSWER_CACHE_DEFAULT_PATH)
    return Path(raw)


def _cache_prompt_version() -> str:
    """Return prompt version marker used for strict cache invalidation."""
    return os.environ.get(
        "RAGAS_ANSWER_CACHE_PROMPT_VERSION",
        ANSWER_CACHE_PROMPT_VERSION,
    )


def _load_answer_cache() -> dict[str, Any]:
    """Load JSON answer cache from disk, returning empty cache on failure."""
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Answer cache load failed for %s: %s", path, exc)
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _save_answer_cache(cache: dict[str, Any]) -> None:
    """Persist JSON answer cache to disk."""
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _build_chunk_fingerprint(chunks: list[dict[str, Any]]) -> str:
    """Build stable hash fingerprint of retrieved chunk identities + content."""
    normalized: list[dict[str, Any]] = []
    for chunk in chunks:
        content = str(chunk.get("content", ""))
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        normalized.append(
            {
                "doc_id": chunk.get("doc_id"),
                "chunk_number": chunk.get("chunk_number"),
                "similarity": chunk.get("similarity"),
                "content_sha256": content_hash,
            }
        )
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_answer_cache_key(
    query: str,
    municipality: Optional[str],
    top_k: int,
    chunks: list[dict[str, Any]],
) -> str:
    """Build strict cache key for generated answers."""
    payload = {
        "query": query,
        "municipality": municipality,
        "top_k": top_k,
        "llm_model": os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514"),
        "prompt_version": _cache_prompt_version(),
        "chunk_fingerprint": _build_chunk_fingerprint(chunks),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Core evaluation function ────────────────────────────────


async def _score_sample(
    sample: SingleTurnSample,
    evaluator_llm: Any,
    evaluator_embeddings: Any,
    *,
    skip_generation_metrics: bool = False,
) -> dict[str, Optional[float]]:
    """
    Score a SingleTurnSample with RAGAs metrics.

    Returns dict with keys: faithfulness, relevancy, context_precision.
    Values are None if the metric was skipped or errored.
    """
    scores: dict[str, Optional[float]] = {
        "faithfulness": None,
        "relevancy": None,
        "context_precision": None,
    }

    # Context precision works even without generation
    try:
        metric = LLMContextPrecisionWithoutReference(llm=evaluator_llm)
        scores["context_precision"] = await metric.single_turn_ascore(sample)
    except Exception as exc:
        print(f"  ⚠ Context precision scoring failed: {type(exc).__name__}: {exc}")
        log.warning("Context precision scoring failed: %s", exc, exc_info=True)

    if skip_generation_metrics:
        return scores

    # Faithfulness — requires response + retrieved_contexts
    try:
        scores["faithfulness"] = await _score_faithfulness(
            sample,
            evaluator_llm,
        )
    except Exception as exc:
        print(f"  ⚠ Faithfulness scoring failed: {type(exc).__name__}: {exc}")
        log.warning("Faithfulness scoring failed: %s", exc, exc_info=True)

    # Answer relevancy — requires user_input + response + embeddings
    if evaluator_embeddings is None:
        msg = (
            "Embeddings unavailable; check langchain_huggingface/"
            "langchain_community import path and embedding model config."
        )
        print(f"  ⚠ Answer relevancy scoring skipped: {msg}")
        log.warning("Answer relevancy scoring skipped: %s", msg)
        return scores

    try:
        metric = AnswerRelevancy(
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
        )
        scores["relevancy"] = await metric.single_turn_ascore(sample)
    except Exception as exc:
        print(f"  ⚠ Answer relevancy scoring failed: {type(exc).__name__}: {exc}")
        log.warning("Answer relevancy scoring failed: %s", exc, exc_info=True)

    return scores


async def _score_faithfulness(
    sample: SingleTurnSample,
    evaluator_llm: Any,
) -> Optional[float]:
    """Score faithfulness with retry for incomplete LLM generations."""
    retries = max(0, int(os.environ.get("RAGAS_FAITH_RETRIES", "2")))
    for attempt in range(retries + 1):
        try:
            metric = Faithfulness(llm=evaluator_llm)
            return await metric.single_turn_ascore(sample)
        except LLMDidNotFinishException as exc:
            if attempt >= retries:
                raise
            wait_s = float(attempt + 1)
            print(
                "  ⚠ Faithfulness incomplete generation; retrying "
                f"({attempt + 1}/{retries}) after {wait_s:.0f}s"
            )
            log.warning(
                "Faithfulness incomplete generation (attempt %s/%s): %s",
                attempt + 1,
                retries,
                exc,
            )
            await asyncio.sleep(wait_s)
    return None


def evaluate_query(
    query_def: dict[str, Any],
    evaluator_llm: Any,
    evaluator_embeddings: Any,
    answer_cache: dict[str, Any],
    cache_enabled: bool,
    cache_stats: CacheStats,
    *,
    retrieval_only: bool = False,
) -> EvalResult:
    """
    Run a single query through retrieve → generate → score.

    Args:
        query_def: Dict with keys: query, municipality, top_k, notes.
        evaluator_llm: Wrapped LLM for RAGAs scoring.
        evaluator_embeddings: Wrapped embeddings for AnswerRelevancy scoring.
        answer_cache: Mutable in-memory cache loaded from JSON.
        cache_enabled: Whether answer caching is enabled.
        cache_stats: Per-run cache hit/miss counters.
        retrieval_only: If True, skip generation and generation-dependent metrics.

    Returns:
        EvalResult with all available scores.
    """
    query = query_def["query"]
    municipality = query_def.get("municipality")
    top_k = query_def.get("top_k", 10)

    # 1. Retrieve
    try:
        result: RetrievalResult = retrieve(
            query, top_k=top_k, municipality=municipality
        )
    except Exception as exc:
        return EvalResult(
            query=query,
            municipality=municipality,
            num_chunks=0,
            top_similarity=0.0,
            error=f"Retrieval failed: {exc}",
        )

    contexts = [c["content"] for c in result.chunks]

    eval_result = EvalResult(
        query=query,
        municipality=municipality,
        num_chunks=result.num_results,
        top_similarity=result.top_similarity,
        latency_retrieval_ms=result.latency_ms,
    )

    # 2. Generate answer (unless retrieval-only mode)
    answer = ""
    if not retrieval_only:
        try:
            from rag.generator import generate_answer

            cache_key = _build_answer_cache_key(
                query=query,
                municipality=municipality,
                top_k=top_k,
                chunks=result.chunks,
            )
            cached = answer_cache.get(cache_key) if cache_enabled else None
            if isinstance(cached, dict) and isinstance(cached.get("answer"), str):
                answer = cached["answer"]
                eval_result.answer_cache_hit = True
                eval_result.latency_generation_ms = 0
                cache_stats.hits += 1
                log.info("Answer cache hit for query '%s'", query[:50])
            else:
                if cache_enabled:
                    cache_stats.misses += 1
                    log.info("Answer cache miss for query '%s'", query[:50])
                gen = generate_answer(query, result.chunks)
                answer = gen.answer
                eval_result.answer_cache_hit = False if cache_enabled else None
                eval_result.latency_generation_ms = gen.latency_ms
                if cache_enabled:
                    answer_cache[cache_key] = {
                        "answer": answer,
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "llm_model": os.environ.get("LLM_MODEL"),
                        "prompt_version": _cache_prompt_version(),
                    }
            eval_result.answer_preview = answer[:200]
        except Exception as exc:
            log.warning("Generation failed for query '%s': %s", query[:50], exc)
            eval_result.error = f"Generation failed: {exc}"
            # Fall through — we can still score context precision
            retrieval_only = True

    # 3. Build RAGAs sample
    sample = SingleTurnSample(
        user_input=query,
        response=answer if answer else "No answer generated.",
        retrieved_contexts=contexts if contexts else ["No context retrieved."],
    )

    # 4. Score with RAGAs
    t0 = time.perf_counter()
    try:
        scores = asyncio.run(
            _score_sample(
                sample,
                evaluator_llm,
                evaluator_embeddings,
                skip_generation_metrics=retrieval_only,
            )
        )
        eval_result.faithfulness = scores["faithfulness"]
        eval_result.relevancy = scores["relevancy"]
        eval_result.context_precision = scores["context_precision"]
    except Exception as exc:
        log.warning("RAGAs scoring failed for query '%s': %s", query[:50], exc)
        if not eval_result.error:
            eval_result.error = f"Scoring failed: {exc}"

    eval_result.latency_scoring_ms = int((time.perf_counter() - t0) * 1000)

    return eval_result


# ── Batch evaluation ─────────────────────────────────────────


def run_evaluation(
    *,
    queries: Optional[list[dict[str, Any]]] = None,
    query_indices: Optional[list[int]] = None,
    retrieval_only: bool = False,
) -> list[EvalResult]:
    """
    Run RAGAs evaluation on the test query suite.

    Args:
        queries: Custom query list. Defaults to TEST_QUERIES.
        query_indices: If set, only run queries at these indices.
        retrieval_only: Skip generation, score only context precision.

    Returns:
        List of EvalResult objects.
    """
    if queries is None:
        queries = TEST_QUERIES

    if query_indices is not None:
        queries = [queries[i] for i in query_indices if i < len(queries)]

    cache_enabled = _env_bool("RAGAS_ANSWER_CACHE_ENABLED", True)
    answer_cache = _load_answer_cache() if cache_enabled else {}
    cache_stats = CacheStats()

    evaluator_llm = _get_evaluator_llm()
    try:
        evaluator_embeddings = _get_evaluator_embeddings()
    except Exception as exc:
        evaluator_embeddings = None
        log.warning("Embeddings initialization failed: %s", exc, exc_info=True)
    results: list[EvalResult] = []

    for i, q in enumerate(queries, 1):
        print(f"\n{'─' * 70}")
        print(f"  [{i}/{len(queries)}] {q['query'][:65]}")
        if q.get("notes"):
            print(f"  Expected: {q['notes']}")
        print(f"{'─' * 70}")

        result = evaluate_query(
            q,
            evaluator_llm,
            evaluator_embeddings,
            answer_cache,
            cache_enabled,
            cache_stats,
            retrieval_only=retrieval_only,
        )
        results.append(result)

        # Print inline result
        _print_result(result)

    # Print summary table
    _print_summary(
        results,
        retrieval_only=retrieval_only,
        cache_enabled=cache_enabled,
        cache_hits=cache_stats.hits,
        cache_misses=cache_stats.misses,
    )

    if cache_enabled:
        _save_answer_cache(answer_cache)

    return results


# ── Display helpers ──────────────────────────────────────────


def _fmt(val: Optional[float]) -> str:
    """Format a metric value for display."""
    if val is None:
        return "  —  "
    return f"{val:.3f}"


def _print_result(result: EvalResult) -> None:
    """Print a single evaluation result."""
    print(f"  Chunks: {result.num_chunks}  "
          f"top_sim: {result.top_similarity:.4f}  "
          f"retrieval: {result.latency_retrieval_ms}ms")

    if result.faithfulness is not None or result.relevancy is not None:
        print(f"  Faithfulness: {_fmt(result.faithfulness)}  "
              f"Relevancy: {_fmt(result.relevancy)}  "
              f"Ctx Precision: {_fmt(result.context_precision)}")

    if result.context_precision is not None and result.faithfulness is None:
        print(f"  Ctx Precision: {_fmt(result.context_precision)}  "
              f"(retrieval-only mode)")

    if result.answer_preview:
        print(f"  Answer: {result.answer_preview[:120]}...")
    if result.answer_cache_hit is True:
        print("  Answer cache: hit")
    if result.answer_cache_hit is False:
        print("  Answer cache: miss")

    if result.error:
        print(f"  ⚠ {result.error}")


def _print_summary(
    results: list[EvalResult],
    *,
    retrieval_only: bool = False,
    cache_enabled: bool = False,
    cache_hits: int = 0,
    cache_misses: int = 0,
) -> None:
    """Print the final summary table."""
    print(f"\n{'═' * 80}")
    print("  RAGAs EVALUATION SUMMARY")
    mode = "retrieval-only" if retrieval_only else "full (retrieve + generate)"
    print(f"  Mode: {mode}")
    print(f"{'═' * 80}")

    # Header
    if retrieval_only:
        print(f"  {'#':>2}  {'Ctx Prec':>8}  {'top_sim':>7}  "
              f"{'chunks':>6}  {'Query':<45}")
        print(f"  {'──':>2}  {'────────':>8}  {'───────':>7}  "
              f"{'──────':>6}  {'─' * 45}")
    else:
        print(f"  {'#':>2}  {'Faith':>6}  {'Relev':>6}  {'CtxPr':>6}  "
              f"{'top_sim':>7}  {'chunks':>6}  {'Query':<35}")
        print(f"  {'──':>2}  {'──────':>6}  {'──────':>6}  {'──────':>6}  "
              f"{'───────':>7}  {'──────':>6}  {'─' * 35}")

    for i, r in enumerate(results):
        q_short = r.query[:43] if retrieval_only else r.query[:33]
        if retrieval_only:
            print(f"  {i:>2}  {_fmt(r.context_precision):>8}  "
                  f"{r.top_similarity:>7.4f}  {r.num_chunks:>6}  {q_short}")
        else:
            print(f"  {i:>2}  {_fmt(r.faithfulness):>6}  "
                  f"{_fmt(r.relevancy):>6}  "
                  f"{_fmt(r.context_precision):>6}  "
                  f"{r.top_similarity:>7.4f}  {r.num_chunks:>6}  {q_short}")

    # Averages
    def _avg(vals: list[Optional[float]]) -> Optional[float]:
        real = [v for v in vals if v is not None]
        return sum(real) / len(real) if real else None

    avg_faith = _avg([r.faithfulness for r in results])
    avg_relev = _avg([r.relevancy for r in results])
    avg_prec = _avg([r.context_precision for r in results])
    avg_sim = _avg([r.top_similarity for r in results])

    print(f"\n{'─' * 80}")
    if retrieval_only:
        print(f"  AVG  {_fmt(avg_prec):>8}  {_fmt(avg_sim):>7}")
    else:
        print(f"  AVG  {_fmt(avg_faith):>6}  {_fmt(avg_relev):>6}  "
              f"{_fmt(avg_prec):>6}  {_fmt(avg_sim):>7}")

    # Pass/fail against AGENTS.md threshold
    if avg_faith is not None:
        status = "✅ PASS" if avg_faith >= 0.85 else "⚠ BELOW THRESHOLD"
        print(f"\n  Faithfulness vs 0.85 target: {avg_faith:.3f} — {status}")

    errored = sum(1 for r in results if r.error)
    if errored:
        print(f"  ⚠ {errored}/{len(results)} queries had errors")
    if cache_enabled and not retrieval_only:
        print(f"  Answer cache: {cache_hits} hit(s), {cache_misses} miss(es)")

    print(f"{'═' * 80}\n")


# ── JSON export ──────────────────────────────────────────────


def export_results(
    results: list[EvalResult],
    output_path: Optional[Path] = None,
) -> Path:
    """Export evaluation results to JSON for tracking."""
    if output_path is None:
        output_path = Path("evaluation/results")
        output_path.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        output_path = output_path / f"ragas_{ts}.json"

    data = []
    for r in results:
        data.append({
            "query": r.query,
            "municipality": r.municipality,
            "num_chunks": r.num_chunks,
            "top_similarity": r.top_similarity,
            "faithfulness": r.faithfulness,
            "relevancy": r.relevancy,
            "context_precision": r.context_precision,
            "latency_retrieval_ms": r.latency_retrieval_ms,
            "latency_generation_ms": r.latency_generation_ms,
            "latency_scoring_ms": r.latency_scoring_ms,
            "answer_cache_hit": r.answer_cache_hit,
            "error": r.error,
        })

    output_path.write_text(json.dumps(data, indent=2))
    print(f"  Results exported to {output_path}")
    return output_path


# ════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="RAGAs evaluation harness for permit_rag"
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip generation, score only context precision",
    )
    parser.add_argument(
        "--query",
        nargs="+",
        type=int,
        default=None,
        help="Run specific queries by index (0-6)",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export results to evaluation/results/ as JSON",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    results = run_evaluation(
        query_indices=args.query,
        retrieval_only=args.retrieval_only,
    )

    if args.export:
        export_results(results)
