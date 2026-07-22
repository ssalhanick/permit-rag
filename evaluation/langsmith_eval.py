"""
evaluation/langsmith_eval.py — LangSmith-native evaluation harness for permit_rag
==================================================================================
Additive to evaluation/ragas_eval.py, not a replacement: RAGAs still owns
faithfulness/relevancy/context-precision + its own answer cache and regression
guard. This harness's value is LangSmith's dataset versioning + experiment
comparison UI on top of that existing infra.

Composes retrieve_with_project() -> guardrail check -> detect_conflicts() ->
generate_answer(), mirroring api/routes/query.py::query_answer's orchestration
without FastAPI DI/auth/background-task plumbing.

Import boundary: evaluation/ -> rag/, db/, standard library only (AGENTS.md).

Requires:
    - ANTHROPIC_API_KEY in .env  (generation + hallucination judge)
    - DATABASE_URL in .env       (retrieval)
    - LANGSMITH_API_KEY in .env  (dataset + experiment upload)

CLI usage:
    py -m evaluation.langsmith_eval                # run against permit_rag_eval_v1
    py -m evaluation.langsmith_eval --dataset permit_rag_security_v1
    py -m evaluation.langsmith_eval --experiment-prefix manual-smoke
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from rag.conflict_detector import detect_conflicts
from rag.generator import generate_answer
from rag.jurisdiction_resolver import municipality_from_address
from rag.permit_classifier import classify_permit_types
from rag.retriever import retrieve_with_project

log = logging.getLogger(__name__)

# Same guardrail constants/semantics as api/routes/query.py and evaluation/ragas_eval.py.
MIN_GROUNDED_CHUNKS = int(os.environ.get("RAG_GUARD_MIN_CHUNKS", "3"))
MIN_GROUNDED_TOP_SIM = float(os.environ.get("RAG_GUARD_MIN_TOP_SIM", "0.74"))

# $ per 1M tokens, (input_rate, output_rate). Extend when LLM_MODEL changes.
_MODEL_RATES_PER_1M: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

DEFAULT_JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "claude-haiku-4-5-20251001")


def _guardrail_triggered(num_chunks: int, top_similarity: float) -> bool:
    """Same guardrail condition as api/routes/query.py::query_answer."""
    return num_chunks < MIN_GROUNDED_CHUNKS or top_similarity < MIN_GROUNDED_TOP_SIM


# ── Target function ──────────────────────────────────────────


def run_pipeline(
    query: str,
    *,
    municipality: str | None = None,
    address: str | None = None,
    project_id: str | None = None,
    top_k: int = 10,
    min_similarity: float = 0.0,
    system_prompt_override: str | None = None,
) -> dict[str, Any]:
    """
    Compose retrieve_with_project() -> guardrail check -> detect_conflicts()
    -> generate_answer(), mirroring api/routes/query.py::query_answer's
    orchestration without FastAPI/auth/background-task plumbing.
    """
    resolved_municipality: str | None = None
    effective_municipality = municipality
    if not effective_municipality and address:
        resolved_municipality = municipality_from_address(address)
        effective_municipality = resolved_municipality

    try:
        permit_types = classify_permit_types(query)
    except Exception as exc:
        log.warning("classify_permit_types failed for %r: %s", query[:50], exc)
        permit_types = []

    result = retrieve_with_project(
        query,
        project_id=project_id,
        top_k=top_k,
        municipality=effective_municipality,
        min_similarity=min_similarity,
    )

    guardrail_on = _guardrail_triggered(result.num_results, result.top_similarity)

    base: dict[str, Any] = {
        "resolved_municipality": resolved_municipality,
        "effective_municipality": effective_municipality,
        "permit_types": permit_types,
        "num_chunks_retrieved": result.num_results,
        "top_similarity": result.top_similarity,
        "guardrail_triggered": guardrail_on,
        "latency_retrieval_ms": result.latency_ms,
        "retrieved_chunk_texts": [c.get("content", "") for c in result.chunks],
    }

    if guardrail_on:
        return {
            **base,
            "answer": "",
            "citations": [],
            "conflict_warnings": [],
            "abstained": True,
            "model": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "latency_generation_ms": None,
        }

    conflicts = detect_conflicts(result.chunks)
    gen = generate_answer(
        query,
        result.chunks,
        project_context=None,
        system_prompt_override=system_prompt_override,
    )

    citations = [
        {"doc_id": c["doc_id"], "chunk_index": c["chunk_index"]}
        for c in gen.citations
        if c.get("found_in_context")
    ]

    return {
        **base,
        "answer": gen.answer,
        "citations": citations,
        "conflict_warnings": [c.detail for c in conflicts],
        "abstained": False,
        "model": gen.model,
        "input_tokens": gen.input_tokens,
        "output_tokens": gen.output_tokens,
        "latency_generation_ms": gen.latency_ms,
    }


def target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Adapter for langsmith.evaluation.evaluate(target, ...)."""
    return run_pipeline(
        inputs["query"],
        municipality=inputs.get("municipality"),
        address=inputs.get("address"),
        project_id=inputs.get("project_id"),
        top_k=inputs.get("top_k", 10),
    )


# ── Deterministic evaluators ─────────────────────────────────


def jurisdiction_correct(run: Any, example: Any) -> dict[str, Any]:
    """Match resolved_municipality (address path) or effective_municipality (direct)."""
    expected = example.outputs.get("expected_resolved_municipality")
    outputs = run.outputs or {}
    if expected is not None:
        actual = outputs.get("resolved_municipality")
    else:
        expected = example.inputs.get("municipality")
        actual = outputs.get("effective_municipality")
    if expected is None and actual is None:
        return {"key": "jurisdiction_accuracy", "score": 1}
    match = (
        isinstance(actual, str)
        and isinstance(expected, str)
        and actual.lower() == expected.lower()
    )
    return {"key": "jurisdiction_accuracy", "score": int(match)}


def _citation_set(citations: list[dict[str, Any]]) -> set[tuple[str, int]]:
    return {(c["doc_id"], c["chunk_index"]) for c in citations}


def citation_precision(run: Any, example: Any) -> dict[str, Any]:
    if example.outputs.get("is_out_of_corpus") or example.outputs.get("skip_citation_check"):
        return {"key": "citation_precision", "score": None}
    expected = _citation_set(example.outputs.get("expected_citations", []))
    actual = _citation_set((run.outputs or {}).get("citations", []))
    if not actual:
        return {"key": "citation_precision", "score": 0}
    return {"key": "citation_precision", "score": len(expected & actual) / len(actual)}


def citation_recall(run: Any, example: Any) -> dict[str, Any]:
    if example.outputs.get("is_out_of_corpus") or example.outputs.get("skip_citation_check"):
        return {"key": "citation_recall", "score": None}
    expected = _citation_set(example.outputs.get("expected_citations", []))
    actual = _citation_set((run.outputs or {}).get("citations", []))
    if not expected:
        return {"key": "citation_recall", "score": 1}
    return {"key": "citation_recall", "score": len(expected & actual) / len(expected)}


def abstention_correct(run: Any, example: Any) -> dict[str, Any]:
    """Did the system abstain exactly when it should have?"""
    expected_abstain = bool(example.outputs.get("is_out_of_corpus"))
    actual_abstain = bool((run.outputs or {}).get("abstained"))
    return {"key": "abstention_correct", "score": int(expected_abstain == actual_abstain)}


def project_isolation_regression(run: Any, example: Any) -> dict[str, Any]:
    """
    Regression guard on retrieve_with_project()'s SQL-level project filter only.
    Does NOT exercise api/routes/query.py's route-level auth (that gap is
    tracked separately -- see evaluation/langsmith_datasets/permit_rag_security_v1.json).
    """
    if example.outputs.get("requires_seed_data"):
        log.info(
            "project_isolation_regression: skipped, requires_seed_data=true "
            "(no private project document exists yet to test against)"
        )
        return {"key": "project_isolation", "score": None}
    forbidden = set(example.outputs.get("expected_forbidden_chunk_doc_ids", []))
    actual_doc_ids = {c["doc_id"] for c in (run.outputs or {}).get("citations", [])}
    leaked = bool(actual_doc_ids & forbidden)
    return {"key": "project_isolation", "score": 0 if leaked else 1}


# ── LLM-as-judge ──────────────────────────────────────────────


_JUDGE_SYSTEM_PROMPT = """\
You are grading a construction-permit RAG answer for groundedness.
Score 1 if every factual claim in the answer is directly supported by the
provided source chunk text. Score 0 if any claim is unsupported, contradicts
the source text, or if the answer states a permit is/isn't required without
that claim being traceable to a cited chunk.
Respond with ONLY a single digit: 1 or 0."""


def hallucination_judge(run: Any, example: Any) -> dict[str, Any]:
    """Claude-Haiku groundedness judge. Skipped for abstained/out-of-corpus runs."""
    outputs = run.outputs or {}
    if outputs.get("abstained") or example.outputs.get("is_out_of_corpus"):
        return {"key": "hallucination_judge", "score": None}

    import anthropic

    answer = outputs.get("answer", "")
    chunk_texts = outputs.get("retrieved_chunk_texts", [])
    reference = example.outputs.get("reference_facts", "")

    user_message = (
        f"QUESTION:\n{example.inputs.get('query', '')}\n\n"
        f"ANSWER TO GRADE:\n{answer}\n\n"
        f"SOURCE CHUNKS:\n" + "\n---\n".join(chunk_texts[:10]) + "\n\n"
        f"WHAT A CORRECT ANSWER COVERS (context only, not sole ground truth):\n{reference}"
    )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model=DEFAULT_JUDGE_MODEL,
        max_tokens=8,
        temperature=0.0,
        system=_JUDGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = response.content[0].text.strip()
    score = 1 if text.startswith("1") else 0
    return {"key": "hallucination_judge", "score": score, "comment": text}


# ── Cost / latency tracking ──────────────────────────────────


def cost_and_latency(run: Any, example: Any) -> dict[str, Any]:
    """Non-pass/fail numeric feedback: cost_usd + total_latency_ms."""
    outputs = run.outputs or {}
    model = outputs.get("model")
    input_tokens = outputs.get("input_tokens", 0) or 0
    output_tokens = outputs.get("output_tokens", 0) or 0
    retrieval_ms = outputs.get("latency_retrieval_ms", 0) or 0
    generation_ms = outputs.get("latency_generation_ms") or 0

    rates = _MODEL_RATES_PER_1M.get(model) if model else None
    if rates is None:
        if model is not None:
            log.warning("cost_and_latency: no rate table entry for model %r", model)
        cost_usd = None
    else:
        input_rate, output_rate = rates
        cost_usd = (input_tokens / 1_000_000 * input_rate) + (
            output_tokens / 1_000_000 * output_rate
        )

    return {
        "key": "cost_and_latency",
        "score": cost_usd,
        "comment": f"total_latency_ms={retrieval_ms + generation_ms}",
    }


ALL_EVALUATORS = [
    jurisdiction_correct,
    citation_precision,
    citation_recall,
    abstention_correct,
    project_isolation_regression,
    hallucination_judge,
    cost_and_latency,
]


# ════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    from api.load_env import bootstrap_env

    bootstrap_env()

    parser = argparse.ArgumentParser(
        description="LangSmith evaluation harness for permit_rag"
    )
    parser.add_argument(
        "--dataset",
        default="permit_rag_eval_v1",
        help="LangSmith dataset name (default: permit_rag_eval_v1)",
    )
    parser.add_argument(
        "--experiment-prefix",
        default=None,
        help="Experiment name prefix shown in the LangSmith UI",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    from langsmith.evaluation import evaluate

    prefix = args.experiment_prefix or f"permit_rag-{int(time.time())}"
    results = evaluate(
        target,
        data=args.dataset,
        evaluators=ALL_EVALUATORS,
        experiment_prefix=prefix,
        metadata={"harness": "langsmith_eval", "dataset": args.dataset},
    )
    print(f"Experiment complete: {prefix}")
    print(results)
