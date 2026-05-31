"""
tests/test_retriever.py — Tests for rag/retriever.py hybrid retrieval
=====================================================================
"""

from __future__ import annotations

from unittest.mock import patch


def test_fuse_with_rrf_prefers_overlap_signal(monkeypatch) -> None:
    """RRF should boost chunks that rank well in both branches."""
    from rag.retriever import _fuse_with_rrf

    monkeypatch.setenv("RETRIEVAL_RRF_K", "60")
    monkeypatch.setenv("RETRIEVAL_RRF_DENSE_WEIGHT", "1.0")
    monkeypatch.setenv("RETRIEVAL_RRF_BM25_WEIGHT", "1.0")

    dense_rows = [
        {"id": "a", "content": "dense a", "doc_id": "d1", "similarity": 0.90},
        {"id": "b", "content": "dense b", "doc_id": "d2", "similarity": 0.80},
    ]
    bm25_rows = [
        {"id": "b", "content": "bm25 b", "doc_id": "d2", "similarity": 0.20},
        {"id": "c", "content": "bm25 c", "doc_id": "d3", "similarity": 0.19},
    ]

    fused = _fuse_with_rrf(dense_rows, bm25_rows, top_k=3)

    assert [row["id"] for row in fused] == ["b", "a", "c"]
    assert fused[0]["dense_rank"] == 2
    assert fused[0]["bm25_rank"] == 1
    assert "rrf_score" in fused[0]


def test_apply_procedural_penalty_uses_rrf_score(monkeypatch) -> None:
    """Post-fusion penalty should preserve RRF-first ordering semantics."""
    from rag.retriever import _apply_procedural_penalty

    monkeypatch.setenv("RETRIEVAL_PROCEDURAL_PENALTY_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_PROCEDURAL_PENALTY", "0.001")
    monkeypatch.setenv("RETRIEVAL_PROCEDURAL_MAX_HITS", "2")

    chunks = [
        {
            "id": "a",
            "content": "permit shall be required",
            "similarity": 0.40,
            "rrf_score": 0.050,
        },
        {
            "id": "b",
            "content": "DULY PASSED AND APPROVED. ATTEST: ordinance no.",
            "similarity": 0.95,
            "rrf_score": 0.049,
        },
    ]
    reranked = _apply_procedural_penalty(chunks, top_k=2)

    assert [row["id"] for row in reranked] == ["a", "b"]
    assert reranked[1]["rrf_score"] < 0.049


@patch("ingestion.embedder.embed_query", return_value=[0.1, 0.2, 0.3])
@patch("db.client.search_chunks_bm25")
@patch("db.client.match_chunks")
def test_retrieve_dense_only_fallback_uses_match_chunks(
    mock_match_chunks,
    mock_search_bm25,
    _mock_embed_query,
    monkeypatch,
) -> None:
    """Hybrid disabled should preserve dense-only retrieval behavior."""
    from rag.retriever import retrieve

    monkeypatch.setenv("RETRIEVAL_HYBRID_ENABLED", "false")
    mock_match_chunks.return_value = [
        {
            "id": "d-1",
            "document_id": "doc-uuid",
            "doc_id": "dallas-fence",
            "content": "A permit is required.",
            "chunk_index": 0,
            "municipality": "dallas",
            "authority_level": "municipal_code",
            "doc_type": "ordinance",
            "document_status": "active",
            "similarity": 0.82,
        }
    ]

    result = retrieve("permit question", top_k=1, municipality="dallas")

    assert result.num_results == 1
    mock_match_chunks.assert_called_once()
    called_top_k = mock_match_chunks.call_args.kwargs["top_k"]
    assert called_top_k == 1
    mock_search_bm25.assert_not_called()


@patch("ingestion.embedder.embed_query", return_value=[0.1, 0.2, 0.3])
@patch("db.client.search_chunks_bm25")
@patch("db.client.match_chunks")
def test_retrieve_hybrid_passes_municipality_to_bm25(
    mock_match_chunks,
    mock_search_bm25,
    _mock_embed_query,
    monkeypatch,
) -> None:
    """Hybrid mode should send municipality filter to BM25 branch."""
    from rag.retriever import retrieve

    monkeypatch.setenv("RETRIEVAL_HYBRID_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_DENSE_TOP_N", "5")
    monkeypatch.setenv("RETRIEVAL_BM25_TOP_N", "7")
    mock_match_chunks.return_value = []
    mock_search_bm25.return_value = [
        {
            "id": "bm25-1",
            "document_id": "doc-uuid",
            "doc_id": "plano-permit",
            "content": "Permit is required for additions.",
            "chunk_index": 2,
            "municipality": "plano",
            "authority_level": "municipal_code",
            "doc_type": "ordinance",
            "document_status": "active",
            "similarity": 0.12,
        }
    ]

    retrieve("plano permit", top_k=3, municipality="plano")

    mock_search_bm25.assert_called_once()
    assert mock_search_bm25.call_args.kwargs["municipality"] == "plano"
    assert mock_search_bm25.call_args.kwargs["top_k"] == 7
