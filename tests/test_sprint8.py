"""
tests/test_sprint8.py — Sprint 8 regression tests
===================================================
Covers:
  Task 16F: tag cited chunks as graph nodes after /query/answer
          - record_cited_chunks() in db/graph_client.py
            - importable and callable
            - issues correct Cypher with expected params
            - no-ops when cited_pairs is empty
            - never raises on connection failure (non-raising contract)
          - /query/answer endpoint wires BackgroundTasks correctly
            - background_tasks.add_task called when cited chunks exist
            - background task NOT scheduled when no cited chunks
            - BackgroundTasks param accepted (no 422 from FastAPI)
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ═══════════════════════════════════════════════════════════════
#  Task 16F — record_cited_chunks() in db/graph_client
# ═══════════════════════════════════════════════════════════════


class TestRecordCitedChunksExists:
    """record_cited_chunks must be importable and have the right signature."""

    def test_function_exists_and_is_callable(self):
        """record_cited_chunks must be importable and callable."""
        from db.graph_client import record_cited_chunks
        assert callable(record_cited_chunks)

    def test_accepts_expected_keyword_args(self):
        """record_cited_chunks must accept query_text, session_id, cited_pairs, cited_at_iso."""
        import inspect
        from db.graph_client import record_cited_chunks
        sig = inspect.signature(record_cited_chunks)
        params = set(sig.parameters.keys())
        assert {"query_text", "session_id", "cited_pairs", "cited_at_iso"} <= params


class TestRecordCitedChunksNoop:
    """record_cited_chunks must skip Neo4j when cited_pairs is empty."""

    def test_noop_on_empty_cited_pairs(self):
        """No Cypher should be issued when cited_pairs is []."""
        import db.graph_client as gc

        mock_driver = MagicMock()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.record_cited_chunks(
                query_text="What is the setback?",
                session_id="sess-001",
                cited_pairs=[],
                cited_at_iso="2026-06-17T03:00:00+00:00",
            )
        # Driver session must never be opened
        mock_driver.session.assert_not_called()


class TestRecordCitedChunksWrites:
    """record_cited_chunks must write correct Cypher when pairs are given."""

    def _mock_driver(self):
        """Return a mock Neo4j driver with a working session context manager."""
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        return mock_driver, mock_session

    def test_session_run_called_with_pairs(self):
        """session.run() must be called once with non-empty cited_pairs list."""
        import db.graph_client as gc

        mock_driver, mock_session = self._mock_driver()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.record_cited_chunks(
                query_text="Fence height limit?",
                session_id="sess-abc",
                cited_pairs=[("dallas-fence-code", 3), ("texas-state", 7)],
                cited_at_iso="2026-06-17T03:00:00+00:00",
            )
        assert mock_session.run.called

    def test_session_id_passed_to_cypher(self):
        """session_id must be forwarded as a Cypher parameter."""
        import db.graph_client as gc

        mock_driver, mock_session = self._mock_driver()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.record_cited_chunks(
                query_text="Setback?",
                session_id="test-session-xyz",
                cited_pairs=[("doc-a", 0)],
                cited_at_iso="2026-06-17T04:00:00+00:00",
            )
        call_kwargs = mock_session.run.call_args[1]
        assert call_kwargs.get("session_id") == "test-session-xyz"

    def test_cited_pairs_serialised_as_lists(self):
        """cited_pairs must be passed as list-of-lists (Neo4j driver compatible)."""
        import db.graph_client as gc

        mock_driver, mock_session = self._mock_driver()
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.record_cited_chunks(
                query_text="Permit fee?",
                session_id="sess-999",
                cited_pairs=[("doc-x", 5)],
                cited_at_iso="2026-06-17T05:00:00+00:00",
            )
        call_kwargs = mock_session.run.call_args[1]
        pairs = call_kwargs.get("cited_pairs")
        assert isinstance(pairs, list)
        assert isinstance(pairs[0], list)  # inner elements are lists, not tuples

    def test_query_text_passed_to_cypher(self):
        """query_text must be forwarded so the Query node is labelled correctly."""
        import db.graph_client as gc

        mock_driver, mock_session = self._mock_driver()
        q = "What are the fire setback rules?"
        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.record_cited_chunks(
                query_text=q,
                session_id="s1",
                cited_pairs=[("doc-fire", 2)],
                cited_at_iso="2026-06-17T06:00:00+00:00",
            )
        call_kwargs = mock_session.run.call_args[1]
        assert call_kwargs.get("query_text") == q


class TestRecordCitedChunksNonRaising:
    """record_cited_chunks must never raise — graph down = WARNING log only."""

    def test_does_not_raise_on_connection_error(self):
        """ConnectionError from Neo4j must be silenced and logged."""
        import db.graph_client as gc

        mock_driver = MagicMock()
        mock_driver.session.side_effect = ConnectionError("Bolt refused")
        with patch.object(gc, "get_driver", return_value=mock_driver):
            # Must not raise
            gc.record_cited_chunks(
                query_text="Any query",
                session_id="sess-fail",
                cited_pairs=[("doc-a", 1)],
                cited_at_iso="2026-06-17T07:00:00+00:00",
            )

    def test_does_not_raise_on_run_exception(self):
        """session.run() throwing must be silenced and not propagate."""
        import db.graph_client as gc

        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.side_effect = RuntimeError("Cypher syntax error")
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session

        with patch.object(gc, "get_driver", return_value=mock_driver):
            gc.record_cited_chunks(
                query_text="Query",
                session_id="sess-err",
                cited_pairs=[("doc-b", 0)],
                cited_at_iso="2026-06-17T08:00:00+00:00",
            )


# ═══════════════════════════════════════════════════════════════
#  Task 16F — BackgroundTasks wired in query_answer
# ═══════════════════════════════════════════════════════════════


class TestQueryAnswerBackgroundTask:
    """query_answer must schedule record_cited_chunks via BackgroundTasks."""

    def _make_cited_keys(self) -> set[tuple[str, int]]:
        """Return a minimal non-empty set of cited (doc_id, chunk_index) pairs."""
        return {("dallas-code", 3), ("texas-state", 7)}

    def test_background_task_scheduled_when_cited_keys_exist(self):
        """add_task must be called when cited_keys is non-empty."""
        from api.routes.query import query_answer
        from fastapi import BackgroundTasks

        # Build a mock that walks through the entire query_answer function
        # without hitting real external services.
        mock_bg = MagicMock(spec=BackgroundTasks)
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "test-session"

        mock_body = MagicMock()
        mock_body.query = "What is the setback?"
        mock_body.top_k = 5
        mock_body.municipality = "dallas"
        mock_body.address = None
        mock_body.min_similarity = 0.0

        # Stub out all heavy dependencies
        mock_chunk = {
            "id": "00000000-0000-0000-0000-000000000001",
            "document_id": "00000000-0000-0000-0000-000000000002",
            "doc_id": "dallas-code",
            "chunk_index": 3,
            "content": "Setback must be 5 feet.",
            "municipality": "dallas",
            "authority_level": "municipal",
            "doc_type": "building_code",
            "document_status": "active",
            "source_tier": 1,
            "similarity": 0.9,
            "raw_similarity": 0.9,
            "reranked_score": 0.9,
            "provenance_weight": 1.0,
            "filtered_out": False,
        }
        mock_result = MagicMock()
        mock_result.chunks = [mock_chunk]
        mock_result.num_results = 1
        mock_result.top_similarity = 0.9
        mock_result.mean_similarity = 0.9
        mock_result.unique_documents = ["dallas-code"]
        mock_result.latency_ms = 50
        mock_result.query = mock_body.query
        mock_result.top_k = 5
        mock_result.municipality = "dallas"
        mock_result.model = "nomic"

        mock_gen = MagicMock()
        mock_gen.answer = "The setback is 5 feet."
        mock_gen.citations = [
            {"doc_id": "dallas-code", "chunk_index": 3, "found_in_context": True,
             "municipality": "dallas", "authority_level": "municipal"}
        ]
        mock_gen.model = "claude-3-haiku"
        mock_gen.input_tokens = 100
        mock_gen.output_tokens = 50
        mock_gen.latency_ms = 200
        mock_gen.chunk_count = 1

        with patch("api.routes.query.retrieve", return_value=mock_result), \
             patch("rag.generator.generate_answer", return_value=mock_gen), \
             patch("rag.permit_classifier.classify_permit_types", return_value=[]), \
             patch("rag.conflict_detector.detect_conflicts", return_value=[]), \
             patch("db.client.get_jurisdiction", return_value=None), \
             patch("api.routes.query._langsmith_enabled", return_value=False), \
             patch("api.routes.query.MIN_GROUNDED_CHUNKS", 1), \
             patch("api.routes.query.MIN_GROUNDED_TOP_SIM", 0.0), \
             patch("db.graph_client.record_cited_chunks") as mock_record:

            result = query_answer(
                body=mock_body,
                request=mock_request,
                background_tasks=mock_bg,
            )

        # BackgroundTasks.add_task must have been called for graph enrichment
        called_funcs = [call_args[0][0] for call_args in mock_bg.add_task.call_args_list]
        assert mock_record in called_funcs

    def test_background_tasks_param_accepted(self):
        """query_answer signature must accept a BackgroundTasks parameter."""
        import inspect
        from api.routes.query import query_answer
        sig = inspect.signature(query_answer)
        assert "background_tasks" in sig.parameters

    def test_background_task_not_scheduled_when_no_cited_keys(self):
        """add_task must NOT be called when the generator produces no in-context citations."""
        from api.routes.query import query_answer
        from fastapi import BackgroundTasks

        mock_bg = MagicMock(spec=BackgroundTasks)
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "test-session-nocite"

        mock_body = MagicMock()
        mock_body.query = "Permit for what?"
        mock_body.top_k = 5
        mock_body.municipality = None
        mock_body.address = None
        mock_body.min_similarity = 0.0

        mock_chunk = {
            "id": "00000000-0000-0000-0000-000000000003",
            "document_id": "00000000-0000-0000-0000-000000000004",
            "doc_id": "dallas-code",
            "chunk_index": 9,
            "content": "Some irrelevant text.",
            "municipality": "dallas",
            "authority_level": "municipal",
            "doc_type": "building_code",
            "document_status": "active",
            "source_tier": 1,
            "similarity": 0.8,
            "raw_similarity": 0.8,
            "reranked_score": 0.8,
            "provenance_weight": 1.0,
            "filtered_out": False,
        }
        mock_result = MagicMock()
        mock_result.chunks = [mock_chunk]
        mock_result.num_results = 1
        mock_result.top_similarity = 0.8
        mock_result.mean_similarity = 0.8
        mock_result.unique_documents = ["dallas-code"]
        mock_result.latency_ms = 40
        mock_result.query = mock_body.query
        mock_result.top_k = 5
        mock_result.municipality = None
        mock_result.model = "nomic"

        mock_gen = MagicMock()
        mock_gen.answer = "I don't know."
        # No in-context citations → cited_keys will be empty
        mock_gen.citations = [
            {"doc_id": "unknown-doc", "chunk_index": 99, "found_in_context": False,
             "municipality": None, "authority_level": None}
        ]
        mock_gen.model = "claude-3-haiku"
        mock_gen.input_tokens = 80
        mock_gen.output_tokens = 10
        mock_gen.latency_ms = 150
        mock_gen.chunk_count = 1

        with patch("api.routes.query.retrieve", return_value=mock_result), \
             patch("rag.generator.generate_answer", return_value=mock_gen), \
             patch("rag.permit_classifier.classify_permit_types", return_value=[]), \
             patch("rag.conflict_detector.detect_conflicts", return_value=[]), \
             patch("db.client.get_jurisdiction", return_value=None), \
             patch("api.routes.query._langsmith_enabled", return_value=False), \
             patch("api.routes.query.MIN_GROUNDED_CHUNKS", 1), \
             patch("api.routes.query.MIN_GROUNDED_TOP_SIM", 0.0), \
             patch("db.graph_client.record_cited_chunks") as mock_record:

            result = query_answer(
                body=mock_body,
                request=mock_request,
                background_tasks=mock_bg,
            )

        # When no in-context citations, add_task must not be called for graph enrichment
        called_funcs = [call_args[0][0] for call_args in mock_bg.add_task.call_args_list]
        assert mock_record not in called_funcs
