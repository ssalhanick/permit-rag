"""
rag/pipeline.py — RAG retrieval pipeline (dense-only, Week 1)
==============================================================
Orchestrates query → embed → retrieve → format for manual eval.
Generation (LLM answer) is handled by rag/generator.py (not yet built).

This module provides:
    - retrieve_and_display(): retrieve + pretty-print for manual eval
    - batch_eval(): run a test suite and produce a quality report

Import boundary: rag/ → db/, audit/, standard library only (AGENTS.md).

CLI usage:
    py -m rag.pipeline "what are the setback requirements for a fence?"
    py -m rag.pipeline --municipality dallas --top-k 10 "fence setback"
    py -m rag.pipeline --batch              # run predefined test queries
"""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass
from typing import Any, Optional

from rag.retriever import RetrievalResult, retrieve

log = logging.getLogger(__name__)

# ── Quality thresholds (will be tuned via RAGAs Week 4–5) ────

SIMILARITY_WARN = 0.35   # below this → likely irrelevant
SIMILARITY_GOOD = 0.50   # above this → likely relevant
MIN_RESULTS_EXPECTED = 3  # warn if fewer chunks returned


# ── Test queries for manual evaluation ───────────────────────

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


# ── Quality assessment ───────────────────────────────────────

@dataclass
class QualityReport:
    """Assessment of a single retrieval result."""

    query: str
    num_results: int
    top_similarity: float
    mean_similarity: float
    unique_docs: list[str]
    latency_ms: int
    verdict: str  # "good", "weak", "miss"
    warnings: list[str]

    def summary_line(self) -> str:
        """One-line summary for batch reporting."""
        icon = {"good": "✅", "weak": "⚠️", "miss": "❌"}[self.verdict]
        return (
            f"{icon} [{self.verdict:4s}] "
            f"top={self.top_similarity:.4f} "
            f"mean={self.mean_similarity:.4f} "
            f"n={self.num_results:2d} "
            f"docs={len(self.unique_docs)} "
            f"{self.latency_ms:5d}ms  "
            f"{self.query[:60]}"
        )


def assess_quality(result: RetrievalResult) -> QualityReport:
    """
    Evaluate retrieval quality with heuristic checks.

    Verdict logic:
        - "miss"  if 0 results or top similarity < SIMILARITY_WARN
        - "weak"  if top similarity < SIMILARITY_GOOD or few results
        - "good"  otherwise
    """
    warnings: list[str] = []

    if result.num_results == 0:
        return QualityReport(
            query=result.query,
            num_results=0,
            top_similarity=0.0,
            mean_similarity=0.0,
            unique_docs=[],
            latency_ms=result.latency_ms,
            verdict="miss",
            warnings=["No results returned"],
        )

    top_sim = result.top_similarity
    mean_sim = result.mean_similarity

    # Determine verdict
    if top_sim < SIMILARITY_WARN:
        verdict = "miss"
        warnings.append(
            f"Top similarity {top_sim:.4f} < warn threshold {SIMILARITY_WARN}"
        )
    elif top_sim < SIMILARITY_GOOD:
        verdict = "weak"
        warnings.append(
            f"Top similarity {top_sim:.4f} < good threshold {SIMILARITY_GOOD}"
        )
    else:
        verdict = "good"

    # Check result count
    if result.num_results < MIN_RESULTS_EXPECTED:
        warnings.append(
            f"Only {result.num_results} results "
            f"(expected >= {MIN_RESULTS_EXPECTED})"
        )
        if verdict == "good":
            verdict = "weak"

    # Check document diversity
    if len(result.unique_documents) == 1 and result.num_results > 3:
        warnings.append(
            "All results from single document — low diversity"
        )

    return QualityReport(
        query=result.query,
        num_results=result.num_results,
        top_similarity=top_sim,
        mean_similarity=mean_sim,
        unique_docs=result.unique_documents,
        latency_ms=result.latency_ms,
        verdict=verdict,
        warnings=warnings,
    )


# ── Display helpers ──────────────────────────────────────────

def format_chunk(chunk: dict[str, Any], rank: int) -> str:
    """Format a single chunk for terminal display."""
    sim = chunk["similarity"]
    doc_id = chunk["doc_id"]
    idx = chunk["chunk_index"]
    muni = chunk["municipality"]
    level = chunk["authority_level"]

    # Similarity indicator
    if sim >= SIMILARITY_GOOD:
        indicator = "🟢"
    elif sim >= SIMILARITY_WARN:
        indicator = "🟡"
    else:
        indicator = "🔴"

    content_preview = textwrap.shorten(
        chunk["content"], width=300, placeholder="..."
    )
    # Wrap for readability
    wrapped = textwrap.fill(
        content_preview, width=80, initial_indent="    ",
        subsequent_indent="    ",
    )

    return (
        f"\n  [{rank}] {indicator} similarity={sim:.4f}  "
        f"doc={doc_id}  chunk={idx}  "
        f"muni={muni}  level={level}\n"
        f"{wrapped}"
    )


def display_result(result: RetrievalResult) -> None:
    """Pretty-print a retrieval result to stdout."""
    print(f"\n{'═' * 80}")
    print(f"  QUERY: {result.query}")
    if result.municipality:
        print(f"  FILTER: municipality={result.municipality}")
    print(f"  top_k={result.top_k}  results={result.num_results}  "
          f"latency={result.latency_ms}ms")
    print(f"{'─' * 80}")

    if not result.chunks:
        print("  ❌ No results returned")
    else:
        for i, chunk in enumerate(result.chunks, 1):
            print(format_chunk(chunk, i))

    # Quality assessment
    report = assess_quality(result)
    print(f"\n{'─' * 80}")
    print(f"  VERDICT: {report.summary_line()}")
    if report.warnings:
        for w in report.warnings:
            print(f"  ⚠  {w}")
    print(f"  Documents: {', '.join(report.unique_docs)}")
    print(f"{'═' * 80}\n")


# ── Single-query entry point ─────────────────────────────────

def retrieve_and_display(
    query: str,
    *,
    top_k: int = 5,
    municipality: Optional[str] = None,
    min_similarity: float = 0.0,
) -> RetrievalResult:
    """
    Run retrieval and display results for manual evaluation.

    Returns the RetrievalResult for programmatic use.
    """
    result = retrieve(
        query,
        top_k=top_k,
        municipality=municipality,
        min_similarity=min_similarity,
    )
    display_result(result)
    return result


# ── Batch evaluation ─────────────────────────────────────────

def batch_eval(
    queries: Optional[list[dict[str, Any]]] = None,
) -> list[QualityReport]:
    """
    Run a batch of test queries and produce a quality summary.

    Args:
        queries: List of query dicts. Defaults to TEST_QUERIES.

    Returns:
        List of QualityReport objects.
    """
    if queries is None:
        queries = TEST_QUERIES

    reports: list[QualityReport] = []

    for i, q in enumerate(queries, 1):
        print(f"\n[{i}/{len(queries)}] {q['query'][:70]}...")
        if q.get("notes"):
            print(f"  Expected: {q['notes']}")

        result = retrieve(
            q["query"],
            top_k=q.get("top_k", 10),
            municipality=q.get("municipality"),
        )
        display_result(result)
        reports.append(assess_quality(result))

    # Summary table
    print(f"\n{'═' * 80}")
    print("  BATCH EVALUATION SUMMARY")
    print(f"{'─' * 80}")

    good = sum(1 for r in reports if r.verdict == "good")
    weak = sum(1 for r in reports if r.verdict == "weak")
    miss = sum(1 for r in reports if r.verdict == "miss")
    avg_latency = (
        sum(r.latency_ms for r in reports) / len(reports)
        if reports else 0
    )

    for r in reports:
        print(f"  {r.summary_line()}")

    print(f"\n{'─' * 80}")
    print(f"  ✅ Good: {good}  ⚠️ Weak: {weak}  ❌ Miss: {miss}")
    print(f"  Avg latency: {avg_latency:.0f}ms")
    print(f"{'═' * 80}\n")

    return reports


# ════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="RAG retrieval pipeline — dense search via pgvector"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Natural-language query (omit for --batch mode)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of chunks to retrieve (default: 10)",
    )
    parser.add_argument(
        "--municipality", "-m",
        default=None,
        help="Filter by municipality (e.g. dallas, plano)",
    )
    parser.add_argument(
        "--min-sim",
        type=float,
        default=0.0,
        help="Minimum similarity threshold (default: 0.0)",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run predefined test queries for batch evaluation",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    if args.batch:
        reports = batch_eval()
    elif args.query:
        retrieve_and_display(
            args.query,
            top_k=args.top_k,
            municipality=args.municipality,
            min_similarity=args.min_sim,
        )
    else:
        parser.print_help()
        print("\nExamples:")
        print('  py -m rag.pipeline "fence setback in Dallas"')
        print('  py -m rag.pipeline -m dallas --top-k 15 "building height"')
        print('  py -m rag.pipeline --batch')
