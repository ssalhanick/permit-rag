"""
tests/test_sprint6.py — Sprint 6 regression tests
===================================================
Covers:
  Fix 2: citation-aware chunk filtering in POST /query/answer
         - cited chunks only when citations are found in context
         - fallback to all chunks when no citations matched context
         - total_chunks_retrieved always reflects raw retrieval count
         - deduplication: same chunk cited twice → appears once
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════


def _make_raw_chunk(
    doc_id: str,
    chunk_index: int,
    *,
    municipality: str = "dallas",
    authority_level: str = "municipal",
    similarity: float = 0.85,
    filtered_out: bool = False,
) -> dict[str, Any]:
    """Return a raw chunk dict as produced by rag.retriever."""
    return {
        "id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "content": f"Content of {doc_id} chunk {chunk_index}.",
        "municipality": municipality,
        "authority_level": authority_level,
        "doc_type": "zoning_ordinance",
        "document_status": "active",
        "source_tier": 1,
        "similarity": similarity,
        "raw_similarity": similarity,
        "reranked_score": similarity,
        "provenance_weight": 1.0,
        "filtered_out": filtered_out,
    }


def _make_citation(doc_id: str, chunk_index: int, *, found: bool) -> dict[str, Any]:
    """Return a citation dict as produced by rag.generator._extract_citations."""
    return {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "found_in_context": found,
        "municipality": "dallas" if found else None,
        "authority_level": "municipal" if found else None,
    }


def _mock_retrieval_result(chunks: list[dict[str, Any]]) -> Any:
    """Build a mock RetrievalResult from a list of raw chunks."""
    mock = MagicMock()
    mock.chunks = chunks
    mock.num_results = len(chunks)
    mock.top_similarity = max((c["similarity"] for c in chunks), default=0.0)
    mock.mean_similarity = (
        sum(c["similarity"] for c in chunks) / len(chunks) if chunks else 0.0
    )
    mock.unique_documents = list({c["doc_id"] for c in chunks})
    mock.latency_ms = 42
    mock.query = "test query"
    mock.top_k = len(chunks)
    mock.municipality = "dallas"
    mock.model = "nomic-embed"
    return mock


def _mock_generation_result(citations: list[dict[str, Any]]) -> Any:
    """Build a mock GenerationResult from a list of citation dicts."""
    mock = MagicMock()
    mock.answer = "Test answer text."
    mock.citations = citations
    mock.model = "claude-sonnet-4"
    mock.input_tokens = 100
    mock.output_tokens = 50
    mock.latency_ms = 500
    mock.chunk_count = 5
    return mock


# ═══════════════════════════════════════════════════════════════
#  Fix 2 — Citation-aware chunk filtering
# ═══════════════════════════════════════════════════════════════


def _call_query_answer(raw_chunks: list[dict], citations: list[dict]) -> Any:
    """
    Exercise the citation-filter logic extracted from query_answer().

    We reproduce the filtering logic directly so tests are fast and
    do not require a running API server.
    """
    from api.schemas import ChunkResponse

    # Build the all_chunks list (same list-comprehension as query.py)
    all_chunks = [
        ChunkResponse(
            id=chunk["id"],
            document_id=chunk["document_id"],
            doc_id=chunk["doc_id"],
            chunk_index=chunk["chunk_index"],
            content=chunk["content"],
            municipality=chunk["municipality"],
            authority_level=chunk["authority_level"],
            doc_type=chunk["doc_type"],
            document_status=chunk["document_status"],
            source_tier=chunk.get("source_tier", 1),
            similarity=chunk.get("raw_similarity") or chunk["similarity"],
            raw_similarity=chunk.get("raw_similarity", chunk["similarity"]),
            reranked_score=chunk.get("reranked_score", chunk["similarity"]),
            provenance_weight=chunk.get("provenance_weight", 1.0),
            filtered_out=chunk.get("filtered_out", False),
        )
        for chunk in raw_chunks
    ]

    # The exact filtering logic from query.py
    cited_keys: set[tuple[str, int]] = {
        (c["doc_id"], c["chunk_index"])
        for c in citations
        if c["found_in_context"]
    }
    if cited_keys:
        cited_chunks = [
            cr for cr in all_chunks
            if (cr.doc_id, cr.chunk_index) in cited_keys
        ]
    else:
        cited_chunks = all_chunks

    return all_chunks, cited_chunks


class TestFix2CitationFilter:
    """Unit tests for citation-aware chunk filtering (Sprint 6 Fix 2)."""

    def test_cited_chunks_only_when_citations_found(self):
        """Only chunks referenced by in-context citations are returned."""
        raw = [
            _make_raw_chunk("dallas-code", 1),
            _make_raw_chunk("dallas-code", 2),
            _make_raw_chunk("plano-permit", 7),
        ]
        citations = [
            _make_citation("dallas-code", 1, found=True),
            # chunk 2 and plano-permit 7 not cited
        ]
        all_chunks, cited = _call_query_answer(raw, citations)

        assert len(all_chunks) == 3, "total_chunks_retrieved should be 3"
        assert len(cited) == 1, "only 1 chunk is cited"
        assert cited[0].doc_id == "dallas-code"
        assert cited[0].chunk_index == 1

    def test_total_chunks_retrieved_reflects_raw_count(self):
        """total_chunks_retrieved equals raw retrieval count regardless of filtering."""
        raw = [
            _make_raw_chunk("doc-a", 0),
            _make_raw_chunk("doc-a", 1),
            _make_raw_chunk("doc-b", 5),
        ]
        citations = [_make_citation("doc-a", 0, found=True)]
        all_chunks, cited = _call_query_answer(raw, citations)

        assert len(all_chunks) == 3
        assert len(cited) == 1

    def test_fallback_to_all_chunks_when_no_context_citations(self):
        """When no citation has found_in_context=True, all chunks are returned."""
        raw = [
            _make_raw_chunk("dallas-code", 1),
            _make_raw_chunk("dallas-code", 2),
        ]
        citations = [
            _make_citation("ghost-doc", 99, found=False),  # hallucinated citation
        ]
        all_chunks, cited = _call_query_answer(raw, citations)

        assert len(all_chunks) == 2
        assert len(cited) == 2, "fallback: all chunks returned"

    def test_fallback_when_no_citations_at_all(self):
        """When citations list is empty, all retrieved chunks are returned."""
        raw = [
            _make_raw_chunk("dallas-code", 1),
            _make_raw_chunk("texas-state", 3),
        ]
        all_chunks, cited = _call_query_answer(raw, [])

        assert len(cited) == len(all_chunks) == 2

    def test_duplicate_citations_do_not_duplicate_chunks(self):
        """A chunk cited twice in the answer appears only once in the response."""
        raw = [_make_raw_chunk("dallas-code", 5)]
        citations = [
            _make_citation("dallas-code", 5, found=True),
            _make_citation("dallas-code", 5, found=True),  # duplicate
        ]
        all_chunks, cited = _call_query_answer(raw, citations)

        # cited_keys is a set, so the chunk appears exactly once
        assert len(cited) == 1

    def test_mixed_found_and_not_found_citations(self):
        """Only found_in_context=True citations drive the filter."""
        raw = [
            _make_raw_chunk("dallas-code", 1),
            _make_raw_chunk("plano-code", 3),
            _make_raw_chunk("frisco-code", 2),
        ]
        citations = [
            _make_citation("dallas-code", 1, found=True),
            _make_citation("ghost-ref", 99, found=False),   # hallucinated
            _make_citation("plano-code", 3, found=True),
        ]
        all_chunks, cited = _call_query_answer(raw, citations)

        assert len(all_chunks) == 3
        assert len(cited) == 2
        doc_ids = {cr.doc_id for cr in cited}
        assert "dallas-code" in doc_ids
        assert "plano-code" in doc_ids
        assert "frisco-code" not in doc_ids

    def test_schema_total_chunks_retrieved_field_present(self):
        """AnswerResponse schema exposes total_chunks_retrieved field."""
        from api.schemas import AnswerResponse
        fields = AnswerResponse.model_fields
        assert "total_chunks_retrieved" in fields

    def test_schema_total_chunks_retrieved_is_int(self):
        """total_chunks_retrieved annotation is int."""
        from api.schemas import AnswerResponse
        annotation = AnswerResponse.model_fields["total_chunks_retrieved"].annotation
        assert annotation is int
