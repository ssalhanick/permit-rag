"""
rag/reranker.py — Provenance-weighted reranker (Sprint 2)
==========================================================
Applies a document-level provenance weight to raw cosine similarity scores,
producing a reranked_score used for final ordering and filtering.

The formula is:
    provenance_weight = retrieval_weight * tier_factor
    reranked_score    = raw_similarity * provenance_weight

Where:
    retrieval_weight  — set per document (1.0 = active corpus, 0.1 = superseded)
    tier_factor       — 1.0 for Tier 1 corpus, 0.9 for Tier 2 user ordinance,
                        0.8 for Tier 3 project documents

Chunks with reranked_score < RETRIEVAL_MIN_RERANKED_SCORE are marked
filtered_out=True but still returned so the frontend can display them greyed-out.

Import boundary: rag/ → standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

# Tier factors — Tier 1 corpus docs are authoritative; user uploads are supplementary.
_TIER_FACTORS: dict[int, float] = {
    1: 1.0,   # corpus (scraped, authoritative)
    2: 0.9,   # user-uploaded ordinance PDF
    3: 0.8,   # user project document (drawings/specs — context only)
}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def provenance_weight(chunk: dict[str, Any]) -> float:
    """
    Compute the provenance multiplier for a single chunk.

    Inputs (from match_chunks() return row):
        retrieval_weight — document-level governance weight (0.0-1.0)
        source_tier      — 1, 2, or 3

    Returns a float in [0, 1].
    """
    base = min(1.0, max(0.0, float(chunk.get("retrieval_weight") or 1.0)))
    tier = int(chunk.get("source_tier") or 1)
    tier_factor = _TIER_FACTORS.get(tier, 1.0)
    return round(min(1.0, base * tier_factor), 6)


def rerank(
    chunks: list[dict[str, Any]],
    *,
    min_reranked_score: float | None = None,
) -> list[dict[str, Any]]:
    """
    Apply provenance weighting to chunks and return them reordered.

    Each chunk in the returned list gains these new keys:
        raw_similarity    — original cosine similarity from pgvector (preserved)
        provenance_weight — the multiplier computed above
        reranked_score    — raw_similarity * provenance_weight
        filtered_out      — True if reranked_score < min_reranked_score

    Chunks are sorted: non-filtered first (by reranked_score DESC),
    then filtered (by reranked_score DESC) so the frontend can show
    them greyed-out at the bottom.

    Args:
        chunks:             List of chunk dicts from retrieve().
        min_reranked_score: Filter threshold. Defaults to env var
                            RETRIEVAL_MIN_RERANKED_SCORE (default 0.3).
    """
    if min_reranked_score is None:
        min_reranked_score = _env_float("RETRIEVAL_MIN_RERANKED_SCORE", 0.3)

    out: list[dict[str, Any]] = []
    for chunk in chunks:
        c = dict(chunk)
        raw_sim = float(c.get("similarity") or 0.0)
        pw = provenance_weight(c)
        rs = round(raw_sim * pw, 6)

        c["raw_similarity"] = raw_sim
        c["provenance_weight"] = pw
        c["reranked_score"] = rs
        c["filtered_out"] = rs < min_reranked_score
        out.append(c)

    # Sort: passing chunks first (reranked_score DESC), then filtered (reranked_score DESC)
    out.sort(key=lambda c: (not c["filtered_out"], c["reranked_score"]), reverse=True)

    passing = sum(1 for c in out if not c["filtered_out"])
    log.info(
        "rerank: %d chunks -> %d passing, %d filtered (threshold=%.3f)",
        len(out), passing, len(out) - passing, min_reranked_score,
    )
    return out
