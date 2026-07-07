"""Unit tests for rag/mini_rag.py merge and conflict helpers."""

from __future__ import annotations

from uuid import uuid4

from rag.mini_rag import (
    detect_corpus_upload_conflicts,
    merge_corpus_and_project,
)


def test_merge_corpus_and_project_dedupes_and_caps() -> None:
    """Merged list should dedupe by chunk id and respect top_k."""
    cid = uuid4()
    corpus = [{"id": cid, "source_tier": 1, "similarity": 0.9, "doc_id": "city-a"}]
    project = [{"id": cid, "source_tier": 3, "similarity": 0.95, "doc_id": "upload-a"}]
    merged = merge_corpus_and_project(corpus, project, top_k=1)
    assert len(merged) == 1
    assert merged[0]["doc_id"] == "city-a"


def test_merge_prefers_lower_source_tier_on_sort() -> None:
    """Tier 1 corpus chunks should sort before tier 3 when merged."""
    corpus = [{"id": uuid4(), "source_tier": 1, "similarity": 0.5, "doc_id": "c1"}]
    project = [{"id": uuid4(), "source_tier": 3, "similarity": 0.99, "doc_id": "p1"}]
    merged = merge_corpus_and_project(corpus, project, top_k=2)
    assert merged[0]["source_tier"] == 1


def test_detect_corpus_upload_conflicts_finds_overlap() -> None:
    """Overlapping permit keywords in corpus + upload should warn."""
    corpus = [{"source_tier": 1, "municipality": "dallas", "doc_id": "d1", "content": "setback 5 feet"}]
    project = [{"source_tier": 3, "municipality": "dallas", "doc_id": "u1", "content": "setback 3 feet"}]
    warnings = detect_corpus_upload_conflicts(corpus, project)
    assert len(warnings) == 1
    assert warnings[0]["subject"] == "user_upload_vs_corpus"
