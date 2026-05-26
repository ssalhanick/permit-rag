"""
rag/retriever.py — Dense retrieval via nomic-embed-text + pgvector
===================================================================
Embeds the user query, calls match_chunks() from db/client.py,
and returns ranked chunks with metadata for the pipeline.

Import boundary: rag/ → db/, standard library only (AGENTS.md).

Usage:
    from rag.retriever import retrieve

    results = retrieve("fence setback requirements in Dallas", top_k=10)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# ── Result dataclass ─────────────────────────────────────────

@dataclass
class RetrievalResult:
    """Container for a single retrieval run."""

    query: str
    chunks: list[dict[str, Any]]
    top_k: int
    municipality: Optional[str]
    latency_ms: int
    model: str = "nomic-ai/nomic-embed-text-v1.5"

    @property
    def num_results(self) -> int:
        """Number of chunks returned."""
        return len(self.chunks)

    @property
    def top_similarity(self) -> float:
        """Highest similarity score, or 0.0 if empty."""
        if not self.chunks:
            return 0.0
        return self.chunks[0]["similarity"]

    @property
    def mean_similarity(self) -> float:
        """Average similarity across returned chunks."""
        if not self.chunks:
            return 0.0
        return sum(c["similarity"] for c in self.chunks) / len(self.chunks)

    @property
    def unique_documents(self) -> list[str]:
        """Distinct doc_ids represented in results."""
        seen: set[str] = set()
        out: list[str] = []
        for c in self.chunks:
            did = c["doc_id"]
            if did not in seen:
                seen.add(did)
                out.append(did)
        return out


# ── Core retrieval function ──────────────────────────────────

def retrieve(
    query: str,
    *,
    top_k: int = 5,
    municipality: Optional[str] = None,
    min_similarity: float = 0.0,
) -> RetrievalResult:
    """
    Embed query and retrieve top-k chunks via dense cosine search.

    Steps:
        1. Embed query with nomic-embed-text (search_query prefix)
        2. Call match_chunks() for pgvector HNSW search
        3. Return results with timing metadata

    Args:
        query: Natural-language question from the user.
        top_k: Maximum chunks to retrieve.
        municipality: Optional filter (e.g. "dallas").
        min_similarity: Discard results below this threshold.

    Returns:
        RetrievalResult with ranked chunks and diagnostics.
    """
    from ingestion.embedder import embed_query

    from db.client import match_chunks

    t0 = time.perf_counter()

    # 1. Embed the query (uses "search_query: " prefix)
    query_vec = embed_query(query)

    # 2. Dense retrieval via pgvector
    chunks = match_chunks(
        query_vec,
        top_k=top_k,
        municipality=municipality,
        min_similarity=min_similarity,
    )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    result = RetrievalResult(
        query=query,
        chunks=chunks,
        top_k=top_k,
        municipality=municipality,
        latency_ms=latency_ms,
    )

    log.info(
        "Retrieved %d chunks in %dms (top_sim=%.4f, mean_sim=%.4f)",
        result.num_results,
        result.latency_ms,
        result.top_similarity,
        result.mean_similarity,
    )

    return result
