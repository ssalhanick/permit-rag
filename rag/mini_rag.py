"""
rag/mini_rag.py — Project-scoped tier 2/3 retrieval (mini-RAG namespace).
============================================================================
Never merges into main corpus governance. Hooks before LLM via merged retrieval.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)


def retrieve_project_chunks(
    query: str,
    project_id: UUID,
    *,
    top_k: int = 5,
    min_similarity: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Embed query and retrieve tier 2/3 chunks scoped to a project.

    Args:
        query: User question text.
        project_id: Active project UUID.
        top_k: Max chunks from project namespace.
        min_similarity: Similarity floor.

    Returns:
        Ranked chunk dicts from db.client.match_project_chunks().
    """
    from db.client import match_project_chunks
    from ingestion.embedder import embed_query

    query_vec = embed_query(query)
    return match_project_chunks(
        query_vec,
        project_id=project_id,
        top_k=top_k,
        min_similarity=min_similarity,
    )


def merge_corpus_and_project(
    corpus_chunks: list[dict[str, Any]],
    project_chunks: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """
    Merge corpus (tier 1) and project (tier 2/3) results.

    Corpus wins on tie (lower source_tier first). Dedupes by chunk id.

    Args:
        corpus_chunks: Tier-1 retrieval hits.
        project_chunks: Tier 2/3 project-scoped hits.
        top_k: Final chunk cap.

    Returns:
        Merged, deduped chunk list.
    """
    seen: set[Any] = set()
    merged: list[dict[str, Any]] = []
    for chunk in corpus_chunks + project_chunks:
        cid = chunk.get("id")
        if cid in seen:
            continue
        seen.add(cid)
        merged.append(chunk)
    merged.sort(
        key=lambda c: (
            int(c.get("source_tier", 1)),
            -(float(c.get("similarity") or 0)),
        ),
    )
    return merged[:top_k]


def detect_corpus_upload_conflicts(
    corpus_chunks: list[dict[str, Any]],
    project_chunks: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    Flag when tier 2/3 upload may contradict tier-1 corpus on same subject.

    Lightweight keyword overlap — full ConflictWarning via conflict_detector.

    Returns:
        List of warning dicts with subject + detail.
    """
    if not corpus_chunks or not project_chunks:
        return []
    warnings: list[dict[str, str]] = []
    for pc in project_chunks:
        if int(pc.get("source_tier", 3)) < 2:
            continue
        for cc in corpus_chunks[:3]:
            if cc.get("municipality") != pc.get("municipality"):
                continue
            if _subjects_overlap(cc.get("content", ""), pc.get("content", "")):
                warnings.append({
                    "subject": "user_upload_vs_corpus",
                    "detail": (
                        f"Project upload [{pc.get('doc_id')}] may differ from "
                        f"corpus [{cc.get('doc_id')}] on overlapping requirements."
                    ),
                })
                break
    return warnings


def _subjects_overlap(text_a: str, text_b: str) -> bool:
    """Return True when both texts mention a shared permit keyword."""
    keywords = ("setback", "egress", "height", "permit", "zoning", "occupancy")
    a = text_a.lower()
    b = text_b.lower()
    return any(k in a and k in b for k in keywords)
