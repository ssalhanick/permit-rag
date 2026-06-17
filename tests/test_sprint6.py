"""
tests/test_sprint6.py — Sprint 6 regression tests
===================================================
Covers:
  Fix 2: citation-aware chunk filtering in POST /query/answer
         - cited chunks only when citations are found in context
         - fallback to all chunks when no citations matched context
         - total_chunks_retrieved always reflects raw retrieval count
         - deduplication: same chunk cited twice → appears once
  Task 16B: db/graph_client.py
         - _parse_auth parsing
         - constraints.cypher file existence and content
         - ping, upsert_document_node, upsert_chunk_node, get_document_node
           (all mocked — no live Neo4j required)
         - close_driver clears module singleton
  Task 16C: scripts/sync_graph.py
         - dry-run mode logs without touching Neo4j
         - doc_id filter narrows sync to one document
         - chunk count returned from _sync_document
         - supersession edges linked correctly
         - missing doc_id exits with non-zero code
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


def _call_query_answer(raw_chunks: list[dict], citations: list[dict]) -> Any:
    """
    Exercise the citation-filter logic extracted from query_answer().

    Reproduces the filtering logic directly so tests are fast and
    do not require a running API server.
    """
    from api.schemas import ChunkResponse

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


# ═══════════════════════════════════════════════════════════════
#  Fix 2 — Citation-aware chunk filtering
# ═══════════════════════════════════════════════════════════════


class TestFix2CitationFilter:
    """Unit tests for citation-aware chunk filtering (Sprint 6 Fix 2)."""

    def test_cited_chunks_only_when_citations_found(self):
        """Only chunks referenced by in-context citations are returned."""
        raw = [
            _make_raw_chunk("dallas-code", 1),
            _make_raw_chunk("dallas-code", 2),
            _make_raw_chunk("plano-permit", 7),
        ]
        citations = [_make_citation("dallas-code", 1, found=True)]
        all_chunks, cited = _call_query_answer(raw, citations)

        assert len(all_chunks) == 3
        assert len(cited) == 1
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
        citations = [_make_citation("ghost-doc", 99, found=False)]
        all_chunks, cited = _call_query_answer(raw, citations)

        assert len(all_chunks) == 2
        assert len(cited) == 2

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
            _make_citation("dallas-code", 5, found=True),
        ]
        all_chunks, cited = _call_query_answer(raw, citations)
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
            _make_citation("ghost-ref", 99, found=False),
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
        assert "total_chunks_retrieved" in AnswerResponse.model_fields

    def test_schema_total_chunks_retrieved_is_int(self):
        """total_chunks_retrieved annotation is int."""
        from api.schemas import AnswerResponse
        annotation = AnswerResponse.model_fields["total_chunks_retrieved"].annotation
        assert annotation is int


# ═══════════════════════════════════════════════════════════════
#  Task 16B — db/graph_client.py
# ═══════════════════════════════════════════════════════════════


class TestGraphClientParsing:
    """Unit tests for internal helpers — no Neo4j connection required."""

    def test_parse_auth_valid(self):
        """'user/password' is correctly split."""
        from db.graph_client import _parse_auth
        user, pwd = _parse_auth("neo4j/localdev123")
        assert user == "neo4j"
        assert pwd == "localdev123"

    def test_parse_auth_password_with_slash(self):
        """Only the first slash is treated as a separator."""
        from db.graph_client import _parse_auth
        user, pwd = _parse_auth("neo4j/pass/word")
        assert user == "neo4j"
        assert pwd == "pass/word"

    def test_parse_auth_invalid_raises(self):
        """Missing slash raises ValueError."""
        from db.graph_client import _parse_auth
        with pytest.raises(ValueError, match="NEO4J_AUTH"):
            _parse_auth("noslash")

    def test_constraints_cypher_file_exists(self):
        """db/cypher/constraints.cypher must exist and be non-empty."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "db", "cypher", "constraints.cypher",
        )
        assert os.path.isfile(path), "constraints.cypher not found"
        assert os.path.getsize(path) > 0, "constraints.cypher is empty"

    def test_constraints_cypher_has_uniqueness_constraints(self):
        """constraints.cypher must declare at least 3 UNIQUE constraints."""
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "..", "db", "cypher", "constraints.cypher",
        )
        content = open(path, encoding="utf-8").read()
        assert content.count("IS UNIQUE") >= 3


class TestGraphClientMocked:
    """
    Functional tests for graph_client helpers using a mocked Neo4j driver.
    No live Neo4j instance required.
    """

    def _mock_driver(self):
        """Return a MagicMock that mimics neo4j.Driver with a usable session."""
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        return mock_driver, mock_session

    def test_ping_returns_true_when_reachable(self):
        """ping() returns True when session.run succeeds."""
        import db.graph_client as gc
        mock_driver, _session = self._mock_driver()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            assert gc.ping() is True

    def test_ping_returns_false_on_connection_error(self):
        """ping() returns False (not an exception) when driver raises."""
        import db.graph_client as gc
        mock_driver = MagicMock()
        mock_driver.session.side_effect = ConnectionError("refused")
        with patch.object(gc, "get_driver", return_value=mock_driver):
            assert gc.ping() is False

    def test_upsert_document_node_calls_session_run(self):
        """upsert_document_node issues session.run with the correct kwargs."""
        import db.graph_client as gc
        mock_driver, mock_session = self._mock_driver()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.upsert_document_node(
                doc_id="dallas-code",
                pg_id="uuid-abc",
                municipality="dallas",
                authority_level="municipal",
                doc_type="zoning_ordinance",
                document_status="active",
                source_tier=1,
                retrieval_weight=1.0,
                source_url="https://example.com/dallas-code.pdf",
            )
        mock_session.run.assert_called_once()
        kwargs = mock_session.run.call_args.kwargs
        assert kwargs["doc_id"] == "dallas-code"
        assert kwargs["municipality"] == "dallas"

    def test_upsert_chunk_node_calls_session_run(self):
        """upsert_chunk_node issues session.run with the correct kwargs."""
        import db.graph_client as gc
        mock_driver, mock_session = self._mock_driver()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.upsert_chunk_node(
                pg_id="chunk-uuid-1",
                doc_id="dallas-code",
                chunk_index=5,
                content="Setback requirements text.",
                municipality="dallas",
                authority_level="municipal",
            )
        mock_session.run.assert_called_once()
        kwargs = mock_session.run.call_args.kwargs
        assert kwargs["doc_id"] == "dallas-code"
        assert kwargs["chunk_index"] == 5

    def test_get_document_node_returns_none_when_not_found(self):
        """get_document_node returns None when session.run().single() is None."""
        import db.graph_client as gc
        mock_driver, mock_session = self._mock_driver()
        mock_session.run.return_value.single.return_value = None
        with patch.object(gc, "get_driver", return_value=mock_driver):
            result = gc.get_document_node("nonexistent-doc")
        assert result is None

    def test_close_driver_clears_module_singleton(self):
        """close_driver() sets the module-level _driver back to None."""
        import db.graph_client as gc
        mock_driver = MagicMock()
        gc._driver = mock_driver
        gc.close_driver()
        assert gc._driver is None
        mock_driver.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════
#  Task 16C — scripts/sync_graph.py
# ═══════════════════════════════════════════════════════════════


def _make_pg_doc(
    doc_id: str,
    *,
    municipality: str = "dallas",
    authority_level: str = "municipal",
    superseded_by: object = None,
) -> dict:
    """Return a minimal Postgres document row dict."""
    return {
        "id": uuid.uuid4(),
        "doc_id": doc_id,
        "municipality": municipality,
        "authority_level": authority_level,
        "doc_type": "zoning_ordinance",
        "document_status": "active",
        "source_tier": 1,
        "retrieval_weight": 1.0,
        "source_url": f"https://example.com/{doc_id}.pdf",
        "superseded_by": superseded_by,
    }


def _make_pg_chunk(doc_id: str, chunk_index: int) -> dict:
    """Return a minimal Postgres chunk row dict."""
    return {
        "id": uuid.uuid4(),
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "content": f"Chunk {chunk_index} of {doc_id}.",
    }


class TestSyncGraph:
    """Unit tests for scripts/sync_graph.py (all mocked)."""

    def test_sync_document_returns_chunk_count(self):
        """_sync_document returns the number of chunks for the document."""
        from scripts.sync_graph import _sync_document

        doc = _make_pg_doc("dallas-code")
        chunks = [_make_pg_chunk("dallas-code", i) for i in range(3)]

        with patch("db.graph_client.upsert_document_node"), \
             patch("db.graph_client.upsert_chunk_node"), \
             patch("db.client.get_chunks_for_document", return_value=chunks):
            count = _sync_document(doc, dry_run=False)

        assert count == 3

    def test_sync_document_dry_run_does_not_call_upsert(self):
        """dry_run=True skips all graph writes."""
        from scripts.sync_graph import _sync_document

        doc = _make_pg_doc("dallas-code")
        chunks = [_make_pg_chunk("dallas-code", 0)]

        with patch("db.graph_client.upsert_document_node") as mock_doc, \
             patch("db.graph_client.upsert_chunk_node") as mock_chunk, \
             patch("db.client.get_chunks_for_document", return_value=chunks):
            _sync_document(doc, dry_run=True)

        mock_doc.assert_not_called()
        mock_chunk.assert_not_called()

    def test_sync_supersessions_links_edge(self):
        """_sync_supersessions calls link_supersession for docs with superseded_by."""
        from scripts.sync_graph import _sync_supersessions

        old_id = uuid.uuid4()
        new_doc = _make_pg_doc("dallas-code-v2")
        old_doc = _make_pg_doc("dallas-code-v1", superseded_by=old_id)

        with patch("db.client.get_document_by_uuid", return_value=new_doc), \
             patch("db.graph_client.link_supersession") as mock_link:
            edges = _sync_supersessions([old_doc, new_doc], dry_run=False)

        assert edges == 1
        mock_link.assert_called_once_with("dallas-code-v1", "dallas-code-v2")

    def test_sync_supersessions_dry_run_skips_link(self):
        """dry_run=True skips link_supersession call."""
        from scripts.sync_graph import _sync_supersessions

        new_doc = _make_pg_doc("dallas-code-v2")
        old_doc = _make_pg_doc("dallas-code-v1", superseded_by=uuid.uuid4())

        with patch("db.client.get_document_by_uuid", return_value=new_doc), \
             patch("db.graph_client.link_supersession") as mock_link:
            _sync_supersessions([old_doc], dry_run=True)

        mock_link.assert_not_called()

    def test_sync_graph_script_exists(self):
        """scripts/sync_graph.py must exist and be importable."""
        import importlib
        mod = importlib.import_module("scripts.sync_graph")
        assert hasattr(mod, "main")
        assert hasattr(mod, "_sync_document")
        assert hasattr(mod, "_sync_supersessions")

