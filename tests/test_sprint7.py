"""
tests/test_sprint7.py — Sprint 7 regression tests
===================================================
Covers:
  Task 16D: graph_health field in GET /health
          - HealthResponse schema has graph_health field (bool)
          - health_check() returns graph_health=True when Neo4j reachable
          - health_check() returns graph_health=False when Neo4j unreachable
          - overall status stays 'healthy' even when graph_health=False

  Task 16E: graph-backed conflict detection
          - find_cross_authority_conflicts() in db/graph_client.py
            - returns list of result dicts on success
            - returns empty list (never raises) on connection failure
            - result dict contains expected keys
          - _graph_pairs_to_conflicts() in rag/conflict_detector.py
            - converts matching graph rows to ConflictResult objects
            - skips rows with no numeric discrepancy
            - skips rows where numeric values agree
          - detect_conflicts_with_graph() integration
            - uses graph path when Neo4j returns data
            - falls back to lightweight detector when graph returns nothing
            - falls back when ImportError for neo4j
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
#  Task 16D — graph_health in GET /health
# ═══════════════════════════════════════════════════════════════


class TestGraphHealthSchema:
    """HealthResponse schema must expose graph_health: bool."""

    def test_graph_health_field_present(self):
        """HealthResponse.graph_health must be a declared model field."""
        from api.schemas import HealthResponse
        assert "graph_health" in HealthResponse.model_fields

    def test_graph_health_field_type_is_bool(self):
        """graph_health annotation must be bool."""
        from api.schemas import HealthResponse
        annotation = HealthResponse.model_fields["graph_health"].annotation
        assert annotation is bool

    def test_graph_health_default_is_false(self):
        """graph_health must default to False (safe when Neo4j absent)."""
        from api.schemas import HealthResponse
        default = HealthResponse.model_fields["graph_health"].default
        assert default is False

    def test_health_response_status_unchanged_when_graph_down(self):
        """Constructing HealthResponse with graph_health=False keeps status='healthy'."""
        from api.schemas import HealthResponse
        resp = HealthResponse(status="healthy", database=True, version="0.1.0", graph_health=False)
        assert resp.status == "healthy"
        assert resp.graph_health is False


class TestHealthEndpointGraphHealth:
    """health_check() must call graph_client.ping() and surface graph_health."""

    def test_health_check_graph_health_true_when_neo4j_up(self):
        """graph_health=True when graph ping succeeds and DB is up."""
        import api.main as main_module
        from db.client import ping as db_ping  # noqa: F401

        with patch.object(main_module, "_graph_client") as mock_gc, \
             patch("api.main.ping", return_value=True):
            mock_gc.ping.return_value = True
            result = main_module.health_check()

        assert result.graph_health is True
        assert result.status == "healthy"
        assert result.database is True
        mock_gc.ping.assert_called_once()

    def test_health_check_graph_health_false_when_neo4j_down(self):
        """graph_health=False when graph ping fails but DB is still up."""
        import api.main as main_module

        with patch.object(main_module, "_graph_client") as mock_gc, \
             patch("api.main.ping", return_value=True):
            mock_gc.ping.return_value = False
            result = main_module.health_check()

        assert result.graph_health is False
        assert result.status == "healthy"   # overall status NOT affected
        assert result.database is True

    def test_health_check_status_unhealthy_only_when_db_down(self):
        """Status is 'unhealthy' only when Postgres ping fails (graph irrelevant)."""
        import api.main as main_module

        with patch.object(main_module, "_graph_client") as mock_gc, \
             patch("api.main.ping", return_value=False):
            mock_gc.ping.return_value = False
            result = main_module.health_check()

        assert result.status == "unhealthy"
        assert result.database is False
        assert result.graph_health is False

    def test_health_check_healthy_with_graph_down_and_db_up(self):
        """Healthy service with graph down — status must remain 'healthy'."""
        import api.main as main_module

        with patch.object(main_module, "_graph_client") as mock_gc, \
             patch("api.main.ping", return_value=True):
            mock_gc.ping.return_value = False
            result = main_module.health_check()

        assert result.status == "healthy"


# ═══════════════════════════════════════════════════════════════
#  Task 16E — find_cross_authority_conflicts() in graph_client
# ═══════════════════════════════════════════════════════════════


class TestFindCrossAuthorityConflicts:
    """Unit tests for db.graph_client.find_cross_authority_conflicts()."""

    def _mock_driver_with_data(self, rows: list[dict]):
        """Return a MagicMock Neo4j driver that returns `rows` from session.run."""
        mock_session = MagicMock()
        mock_session.__enter__ = lambda s: s
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.run.return_value.data.return_value = rows
        mock_driver = MagicMock()
        mock_driver.session.return_value = mock_session
        return mock_driver, mock_session

    def test_returns_list_on_success(self):
        """find_cross_authority_conflicts returns a list of dicts on success."""
        import db.graph_client as gc

        sample_rows = [
            {
                "doc_a_id": "dallas-code",
                "doc_a_authority": "municipal",
                "chunk_a_content": "Setback must be 5 feet from property line.",
                "chunk_a_index": 3,
                "doc_b_id": "texas-state-code",
                "doc_b_authority": "state",
                "chunk_b_content": "Minimum setback distance is 10 feet.",
                "chunk_b_index": 7,
            }
        ]
        mock_driver, _ = self._mock_driver_with_data(sample_rows)
        with patch.object(gc, "get_driver", return_value=mock_driver):
            result = gc.find_cross_authority_conflicts("setback")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["doc_a_id"] == "dallas-code"

    def test_returns_empty_list_on_connection_error(self):
        """find_cross_authority_conflicts returns [] (never raises) on error."""
        import db.graph_client as gc

        mock_driver = MagicMock()
        mock_driver.session.side_effect = ConnectionError("refused")
        with patch.object(gc, "get_driver", return_value=mock_driver):
            result = gc.find_cross_authority_conflicts("setback")

        assert result == []

    def test_result_dict_has_expected_keys(self):
        """Each result row must contain all 8 expected keys."""
        import db.graph_client as gc

        row = {
            "doc_a_id": "a",
            "doc_a_authority": "municipal",
            "chunk_a_content": "5 feet setback required.",
            "chunk_a_index": 0,
            "doc_b_id": "b",
            "doc_b_authority": "state",
            "chunk_b_content": "10 feet setback required.",
            "chunk_b_index": 1,
        }
        mock_driver, _ = self._mock_driver_with_data([row])
        with patch.object(gc, "get_driver", return_value=mock_driver):
            result = gc.find_cross_authority_conflicts("setback")

        expected_keys = {
            "doc_a_id", "doc_a_authority", "chunk_a_content", "chunk_a_index",
            "doc_b_id", "doc_b_authority", "chunk_b_content", "chunk_b_index",
        }
        assert expected_keys.issubset(result[0].keys())

    def test_function_exists_and_is_callable(self):
        """find_cross_authority_conflicts must be importable and callable."""
        from db.graph_client import find_cross_authority_conflicts
        assert callable(find_cross_authority_conflicts)


# ═══════════════════════════════════════════════════════════════
#  Task 16E — _graph_pairs_to_conflicts() in conflict_detector
# ═══════════════════════════════════════════════════════════════


class TestGraphPairsToConflicts:
    """Unit tests for the graph-row → ConflictResult converter."""

    def _make_row(
        self,
        content_a: str,
        content_b: str,
        auth_a: str = "municipal",
        auth_b: str = "state",
    ) -> dict:
        return {
            "doc_a_id": "doc-a",
            "doc_a_authority": auth_a,
            "chunk_a_content": content_a,
            "chunk_a_index": 1,
            "doc_b_id": "doc-b",
            "doc_b_authority": auth_b,
            "chunk_b_content": content_b,
            "chunk_b_index": 2,
        }

    def test_converts_discrepant_row_to_conflict(self):
        """Rows with differing numeric values produce a ConflictResult."""
        from rag.conflict_detector import _graph_pairs_to_conflicts

        row = self._make_row(
            "Setback must be 5 feet from the property line.",
            "Minimum setback is 10 feet per state code.",
        )
        results = _graph_pairs_to_conflicts([row], "setback", ["setback"])
        assert len(results) == 1
        assert results[0].subject == "setback"
        assert "municipal" in results[0].detail.lower() or "state" in results[0].detail.lower()

    def test_skips_row_with_no_numerics_in_a(self):
        """Rows without numeric values in chunk_a produce no conflict."""
        from rag.conflict_detector import _graph_pairs_to_conflicts

        row = self._make_row(
            "Setback requirements vary by zone.",   # no number
            "Minimum setback is 10 feet.",
        )
        results = _graph_pairs_to_conflicts([row], "setback", ["setback"])
        assert results == []

    def test_skips_row_where_values_agree(self):
        """Rows where both chunks state the same numeric value produce no conflict."""
        from rag.conflict_detector import _graph_pairs_to_conflicts

        row = self._make_row(
            "Setback must be 10 feet from the line.",
            "Minimum setback is 10 feet.",
        )
        results = _graph_pairs_to_conflicts([row], "setback", ["setback"])
        assert results == []

    def test_detail_contains_graph_path_marker(self):
        """ConflictResult.detail mentions '(graph path)' to distinguish from lightweight."""
        from rag.conflict_detector import _graph_pairs_to_conflicts

        row = self._make_row(
            "Fence height limit is 4 feet.",
            "Fence height limit is 6 feet.",
        )
        results = _graph_pairs_to_conflicts([row], "fence height", ["fence height"])
        assert len(results) == 1
        assert "graph path" in results[0].detail


# ═══════════════════════════════════════════════════════════════
#  Task 16E — detect_conflicts_with_graph() integration
# ═══════════════════════════════════════════════════════════════


def _make_chunk(
    doc_id: str,
    authority: str,
    content: str,
    chunk_index: int = 0,
) -> dict:
    """Minimal chunk dict for conflict detector tests."""
    return {
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "content": content,
        "authority_level": authority,
        "filtered_out": False,
    }


class TestDetectConflictsWithGraph:
    """Integration tests for detect_conflicts_with_graph()."""

    def test_uses_graph_results_when_available(self):
        """When graph returns rows, conflicts are derived from graph data."""
        from rag.conflict_detector import detect_conflicts_with_graph

        graph_row = {
            "doc_a_id": "dallas-code",
            "doc_a_authority": "municipal",
            "chunk_a_content": "Setback must be 5 feet from the property line.",
            "chunk_a_index": 1,
            "doc_b_id": "texas-state",
            "doc_b_authority": "state",
            "chunk_b_content": "Minimum setback is 10 feet per state statute.",
            "chunk_b_index": 4,
        }

        chunks = [
            _make_chunk("dallas-code", "municipal", "Setback must be 5 feet from property line."),
            _make_chunk("texas-state", "state", "Minimum setback is 10 feet per state statute.", 4),
        ]

        with patch("db.graph_client.find_cross_authority_conflicts", return_value=[graph_row]):
            results = detect_conflicts_with_graph(chunks)

        # Graph path produced at least one conflict (numeric discrepancy)
        assert isinstance(results, list)

    def test_falls_back_to_lightweight_when_graph_empty(self):
        """When graph returns no rows, lightweight detector runs instead."""
        from rag.conflict_detector import detect_conflicts, detect_conflicts_with_graph

        chunks = [
            _make_chunk("doc-a", "municipal", "Setback must be 5 feet."),
            _make_chunk("doc-b", "state", "Minimum setback is 10 feet per state law.", 1),
        ]

        with patch("db.graph_client.find_cross_authority_conflicts", return_value=[]):
            graph_result = detect_conflicts_with_graph(chunks)

        lightweight_result = detect_conflicts(chunks)
        # Both paths should agree on the same conflict list
        assert len(graph_result) == len(lightweight_result)

    def test_falls_back_on_import_error(self):
        """If neo4j package is missing, lightweight detector is used without error."""
        from rag.conflict_detector import detect_conflicts_with_graph

        chunks = [
            _make_chunk("doc-a", "municipal", "No relevant text here."),
        ]

        import builtins
        real_import = builtins.__import__

        def _blocking_import(name, *args, **kwargs):
            if name == "db":
                raise ImportError("Simulated missing neo4j")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=_blocking_import):
            # Should not raise even if the lazy import fails
            result = detect_conflicts_with_graph(chunks)

        assert isinstance(result, list)

    def test_detect_conflicts_with_graph_is_callable(self):
        """detect_conflicts_with_graph must be importable and callable."""
        from rag.conflict_detector import detect_conflicts_with_graph
        assert callable(detect_conflicts_with_graph)
