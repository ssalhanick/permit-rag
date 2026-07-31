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
@patch("db.client.get_jurisdiction_chain")
def test_retrieve_dense_only_fallback_uses_match_chunks(
    mock_get_chain,
    mock_match_chunks,
    mock_search_bm25,
    _mock_embed_query,
    monkeypatch,
) -> None:
    """Hybrid disabled should preserve dense-only retrieval behavior."""
    from rag.retriever import retrieve

    monkeypatch.setenv("RETRIEVAL_HYBRID_ENABLED", "false")
    mock_get_chain.return_value = ["dallas", "dallas-county", "texas", "federal"]
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
    mock_get_chain.assert_called_once_with("dallas")
    mock_match_chunks.assert_called_once()
    called_top_k = mock_match_chunks.call_args.kwargs["top_k"]
    assert called_top_k == 1
    assert mock_match_chunks.call_args.kwargs["municipalities"] == mock_get_chain.return_value
    mock_search_bm25.assert_not_called()


@patch("ingestion.embedder.embed_query", return_value=[0.1, 0.2, 0.3])
@patch("db.client.search_chunks_bm25")
@patch("db.client.match_chunks")
@patch("db.client.get_jurisdiction_chain")
def test_retrieve_hybrid_passes_jurisdiction_chain_to_bm25(
    mock_get_chain,
    mock_match_chunks,
    mock_search_bm25,
    _mock_embed_query,
    monkeypatch,
) -> None:
    """Hybrid mode should send the expanded jurisdiction chain to the BM25 branch."""
    from rag.retriever import retrieve

    monkeypatch.setenv("RETRIEVAL_HYBRID_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_DENSE_TOP_N", "5")
    monkeypatch.setenv("RETRIEVAL_BM25_TOP_N", "7")
    mock_get_chain.return_value = ["plano", "collin-county", "texas", "federal"]
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

    mock_get_chain.assert_called_once_with("plano")
    mock_search_bm25.assert_called_once()
    assert mock_search_bm25.call_args.kwargs["municipalities"] == mock_get_chain.return_value
    assert mock_search_bm25.call_args.kwargs["top_k"] == 7


@patch("ingestion.embedder.embed_query", return_value=[0.1, 0.2, 0.3])
@patch("db.client.match_chunks")
@patch("db.client.get_jurisdiction_chain")
def test_retrieve_without_municipality_skips_chain_lookup(
    mock_get_chain,
    mock_match_chunks,
    _mock_embed_query,
    monkeypatch,
) -> None:
    """No municipality given should mean no DB round trip for a chain, and no filter."""
    from rag.retriever import retrieve

    monkeypatch.setenv("RETRIEVAL_HYBRID_ENABLED", "false")
    mock_match_chunks.return_value = []

    retrieve("what permits do I need", top_k=3)

    mock_get_chain.assert_not_called()
    assert mock_match_chunks.call_args.kwargs["municipalities"] is None


@patch("ingestion.embedder.embed_query", return_value=[0.1, 0.2, 0.3])
@patch("db.client.get_jurisdiction_chain", return_value=["dallas"])
@patch("db.client.search_chunks_bm25", return_value=[])
@patch("db.client.match_chunks", return_value=[])
@patch("db.client.get_project")
@patch("rag.mini_rag.retrieve_project_chunks", return_value=[])
@patch("rag.mini_rag.retrieve_overlay_chunks")
def test_retrieve_with_project_merges_overlay_chunks(
    mock_overlay,
    _mock_project_chunks,
    mock_get_project,
    _mock_match_chunks,
    _mock_bm25,
    _mock_chain,
    _mock_embed,
) -> None:
    """An approved overlay's chunks should surface for any project inside its
    boundary, merged in alongside the project's own tier 2/3 chunks."""
    from uuid import uuid4

    from rag.retriever import retrieve_with_project

    project_id = str(uuid4())
    mock_get_project.return_value = {"latitude": 32.8, "longitude": -96.78}
    mock_overlay.return_value = [
        {"id": "overlay-chunk-1", "source_tier": 3, "similarity": 0.9, "doc_id": "swiss-ave"}
    ]

    result = retrieve_with_project("historic district rules", project_id=project_id, top_k=5)

    mock_overlay.assert_called_once_with(
        "historic district rules", latitude=32.8, longitude=-96.78, top_k=3, min_similarity=0.0,
    )
    assert any(c["doc_id"] == "swiss-ave" for c in result.chunks)


@patch("ingestion.embedder.embed_query", return_value=[0.1, 0.2, 0.3])
@patch("db.client.get_jurisdiction_chain", return_value=["dallas"])
@patch("db.client.search_chunks_bm25", return_value=[])
@patch("db.client.match_chunks", return_value=[])
@patch("db.client.get_project")
@patch("rag.mini_rag.retrieve_project_chunks", return_value=[])
@patch("rag.mini_rag.retrieve_overlay_chunks")
def test_retrieve_with_project_skips_overlay_lookup_without_coordinates(
    mock_overlay,
    _mock_project_chunks,
    mock_get_project,
    _mock_match_chunks,
    _mock_bm25,
    _mock_chain,
    _mock_embed,
) -> None:
    """A project with no lat/lng on file shouldn't attempt an overlay lookup at all."""
    from uuid import uuid4

    from rag.retriever import retrieve_with_project

    project_id = str(uuid4())
    mock_get_project.return_value = {"latitude": None, "longitude": None}

    retrieve_with_project("some query", project_id=project_id, top_k=5)

    mock_overlay.assert_not_called()


def test_non_muni_guardrail_boosts_state_for_texas_query(monkeypatch) -> None:
    """Statewide query should downrank municipal noise under hybrid scoring."""
    from rag.retriever import _apply_non_municipal_authority_guardrails

    monkeypatch.setenv("RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_NON_MUNI_MUNICIPAL_PENALTY", "0.08")
    monkeypatch.setenv("RETRIEVAL_NON_MUNI_SCOPE_MATCH_BONUS", "0.02")
    monkeypatch.setenv("RETRIEVAL_NON_MUNI_SCOPE_MISMATCH_PENALTY", "0.03")

    chunks = [
        {
            "id": "dallas-1",
            "authority_level": "municipal",
            "rrf_score": 0.100,
            "similarity": 0.86,
        },
        {
            "id": "tx-1",
            "authority_level": "state",
            "rrf_score": 0.095,
            "similarity": 0.80,
        },
    ]

    reranked = _apply_non_municipal_authority_guardrails(
        chunks,
        query="Do I need a permit for electrical work in Texas?",
        municipality=None,
        top_k=2,
    )

    assert [row["id"] for row in reranked] == ["tx-1", "dallas-1"]
    assert reranked[0]["authority_guardrail_bonus"] > 0.0
    assert reranked[1]["authority_guardrail_penalty"] > 0.0


def test_non_muni_guardrail_skips_municipality_filtered_queries(monkeypatch) -> None:
    """Municipality-filtered retrieval should not get authority penalties."""
    from rag.retriever import _apply_non_municipal_authority_guardrails

    monkeypatch.setenv("RETRIEVAL_AUTHORITY_GUARDRAIL_ENABLED", "true")
    chunks = [{"id": "dallas-1", "authority_level": "municipal", "similarity": 0.90}]

    reranked = _apply_non_municipal_authority_guardrails(
        chunks,
        query="What are Dallas fence setbacks?",
        municipality="dallas",
        top_k=1,
    )

    assert reranked == chunks
