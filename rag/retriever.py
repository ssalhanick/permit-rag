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
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

log = logging.getLogger(__name__)
PROCEDURAL_REGEX = (
    re.compile(r"\bduly passed and approved\b", re.IGNORECASE),
    re.compile(r"\battest:\b", re.IGNORECASE),
    re.compile(r"\bapproved as to form\b", re.IGNORECASE),
    re.compile(r"\badopting and enacting supplement\b", re.IGNORECASE),
    re.compile(r"\bordinance no\.\b", re.IGNORECASE),
)
STATE_SCOPE_REGEX = re.compile(r"\b(texas|statewide|state law|state code)\b", re.IGNORECASE)
FEDERAL_SCOPE_REGEX = re.compile(r"\b(federal|osha|epa|cfr|u\.?s\.?c\.?)\b", re.IGNORECASE)
ADA_SCOPE_REGEX = re.compile(r"\b(ada|accessibility)\b", re.IGNORECASE)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """Parse a float environment variable with fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable with fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _count_procedural_hits(text: str) -> int:
    """Count procedural phrase hits in a chunk text."""
    return sum(len(pattern.findall(text)) for pattern in PROCEDURAL_REGEX)


def _score_key(chunk: dict[str, Any]) -> str:
    """Return the ranking key currently used for this chunk."""
    return "rrf_score" if chunk.get("rrf_score") is not None else "similarity"


def _detect_query_authority_targets(query: str) -> set[str]:
    """Infer desired authority scope for non-municipality queries."""
    targets: set[str] = set()
    q = query.strip().lower()
    if STATE_SCOPE_REGEX.search(q):
        targets.add("state")
    if FEDERAL_SCOPE_REGEX.search(q):
        targets.add("federal")
    if ADA_SCOPE_REGEX.search(q):
        targets.update({"state", "federal"})
    return targets


def _apply_non_municipal_authority_guardrails(
    chunks: list[dict[str, Any]],
    *,
    query: str,
    municipality: Optional[str],
    top_k: int,
) -> list[dict[str, Any]]:
    """Downrank municipal authority when query has no municipality filter."""
    if municipality is not None:
        return chunks[:top_k]
    if not _env_bool("RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED", True):
        return chunks[:top_k]
    municipal_penalty = _env_float("RETRIEVAL_NON_MUNI_MUNICIPAL_PENALTY", 0.06)
    scope_bonus = _env_float("RETRIEVAL_NON_MUNI_SCOPE_MATCH_BONUS", 0.02)
    scope_mismatch = _env_float("RETRIEVAL_NON_MUNI_SCOPE_MISMATCH_PENALTY", 0.03)
    targets = _detect_query_authority_targets(query)
    reranked: list[dict[str, Any]] = []
    for chunk in chunks:
        updated = dict(chunk)
        key = _score_key(updated)
        raw = updated.get(key)
        score = float(raw) if raw is not None else 0.0
        authority = str(updated.get("authority_level") or "").lower()
        penalty = municipal_penalty if authority == "municipal" else 0.0
        bonus = scope_bonus if targets and authority in targets else 0.0
        if targets and authority in {"state", "federal"} and authority not in targets:
            penalty += scope_mismatch
        updated[key] = max(0.0, score - penalty + bonus)
        updated["authority_guardrail_penalty"] = penalty
        updated["authority_guardrail_bonus"] = bonus
        reranked.append(updated)
    reranked.sort(
        key=lambda c: (float(c.get("rrf_score") or 0.0), float(c.get("similarity") or 0.0)),
        reverse=True,
    )
    return reranked[:top_k]


def _apply_procedural_penalty(chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """Downrank procedural-heavy chunks via similarity penalty and rerank."""
    if not _env_bool("RETRIEVAL_PROCEDURAL_PENALTY_ENABLED", True):
        return chunks
    base_penalty = _env_float("RETRIEVAL_PROCEDURAL_PENALTY", 0.015)
    max_hits = int(_env_float("RETRIEVAL_PROCEDURAL_MAX_HITS", 4))
    reranked: list[dict[str, Any]] = []
    for chunk in chunks:
        updated = dict(chunk)
        base_key = _score_key(chunk)
        raw_score = chunk.get(base_key)
        score = float(raw_score) if raw_score is not None else 0.0
        hits = _count_procedural_hits(str(chunk.get("content", "")))
        penalty = base_penalty * min(hits, max_hits)
        updated[base_key] = max(0.0, score - penalty)
        updated["procedural_hits"] = hits
        reranked.append(updated)
    reranked.sort(
        key=lambda c: (
            float(c.get("rrf_score") or 0.0),
            float(c.get("similarity") or 0.0),
        ),
        reverse=True,
    )
    return reranked[:top_k]


def _fuse_with_rrf(
    dense_rows: list[dict[str, Any]],
    bm25_rows: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Fuse dense and BM25 ranked lists using Reciprocal Rank Fusion."""
    rrf_k = _env_int("RETRIEVAL_RRF_K", 60)
    dense_weight = _env_float("RETRIEVAL_RRF_DENSE_WEIGHT", 1.0)
    bm25_weight = _env_float("RETRIEVAL_RRF_BM25_WEIGHT", 1.0)
    by_id: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}

    def _add(rows: list[dict[str, Any]], label: str, weight: float) -> None:
        for rank, row in enumerate(rows, start=1):
            key = str(row["id"])
            if key not in by_id:
                merged = dict(row)
                merged["dense_rank"] = None
                merged["bm25_rank"] = None
                by_id[key] = merged
            by_id[key][f"{label}_rank"] = rank
            scores[key] = scores.get(key, 0.0) + (weight / (rrf_k + rank))

    _add(dense_rows, "dense", dense_weight)
    _add(bm25_rows, "bm25", bm25_weight)

    fused = sorted(
        by_id.items(),
        key=lambda item: (scores[item[0]], float(item[1].get("similarity") or 0.0)),
        reverse=True,
    )
    out: list[dict[str, Any]] = []
    for key, row in fused[:top_k]:
        merged = dict(row)
        merged["rrf_score"] = scores[key]
        out.append(merged)
    return out


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
        top = self.chunks[0].get("similarity")
        return float(top) if top is not None else 0.0

    @property
    def mean_similarity(self) -> float:
        """Average similarity across returned chunks."""
        if not self.chunks:
            return 0.0
        sims = [float(c["similarity"]) for c in self.chunks if c.get("similarity") is not None]
        if not sims:
            return 0.0
        return sum(sims) / len(sims)

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

    from db.client import match_chunks, search_chunks_bm25

    t0 = time.perf_counter()

    # 1. Embed the query (uses "search_query: " prefix)
    query_vec = embed_query(query)

    hybrid_enabled = _env_bool("RETRIEVAL_HYBRID_ENABLED", False)
    dense_top_n = max(top_k, _env_int("RETRIEVAL_DENSE_TOP_N", 20))
    bm25_top_n = max(top_k, _env_int("RETRIEVAL_BM25_TOP_N", 20))

    dense_chunks = match_chunks(
        query_vec,
        top_k=dense_top_n if hybrid_enabled else top_k,
        municipality=municipality,
        min_similarity=min_similarity,
    )
    if hybrid_enabled:
        bm25_chunks = search_chunks_bm25(
            query,
            top_k=bm25_top_n,
            municipality=municipality,
        )
        chunks = _fuse_with_rrf(dense_chunks, bm25_chunks, top_k=top_k)
    else:
        chunks = dense_chunks
    chunks = _apply_non_municipal_authority_guardrails(
        chunks,
        query=query,
        municipality=municipality,
        top_k=top_k,
    )
    chunks = _apply_procedural_penalty(chunks, top_k)

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
