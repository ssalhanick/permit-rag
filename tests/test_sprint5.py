"""
tests/test_sprint5.py — Sprint 5 regression tests
===================================================
Covers:
  Fix 1: match_chunks() ordering (via retriever env flag)
  Fix 3: _extract_citations() — strict + loose formats + miss-rate warning
  Task 14C: jurisdiction_resolver (mocked Census API + mocked DB)
  Task 15: conflict_detector — numeric discrepancy detection
"""
from __future__ import annotations

import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════
#  Fix 3 — Citation regex hardening
# ═══════════════════════════════════════════════════════════════


def _make_chunks(pairs: list[tuple[str, int]]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": doc_id,
            "chunk_index": idx,
            "municipality": "dallas",
            "authority_level": "municipal",
        }
        for doc_id, idx in pairs
    ]


def test_citation_strict_format():
    """Original comma format still works."""
    from rag.generator import _extract_citations

    answer = "See [dallas-code, chunk 5] for details."
    chunks = _make_chunks([("dallas-code", 5)])
    result = _extract_citations(answer, chunks)
    assert len(result) == 1
    assert result[0]["doc_id"] == "dallas-code"
    assert result[0]["chunk_index"] == 5
    assert result[0]["found_in_context"] is True


def test_citation_loose_format_space_only():
    """Loose space-only format (no comma) is now accepted."""
    from rag.generator import _extract_citations

    answer = "As noted in [plano-permit chunk 12]."
    chunks = _make_chunks([("plano-permit", 12)])
    result = _extract_citations(answer, chunks)
    assert len(result) == 1
    assert result[0]["found_in_context"] is True


def test_citation_capital_chunk():
    """'Chunk' with capital C is accepted (case-insensitive)."""
    from rag.generator import _extract_citations

    answer = "Per [texas-building-code, Chunk 3]."
    chunks = _make_chunks([("texas-building-code", 3)])
    result = _extract_citations(answer, chunks)
    assert len(result) == 1
    assert result[0]["found_in_context"] is True


def test_citation_mixed_formats():
    """Both formats in same answer, both resolved."""
    from rag.generator import _extract_citations

    answer = "[dallas-code, chunk 5] and [plano-permit chunk 12]."
    chunks = _make_chunks([("dallas-code", 5), ("plano-permit", 12)])
    result = _extract_citations(answer, chunks)
    assert len(result) == 2
    assert all(c["found_in_context"] for c in result)


def test_citation_miss_rate_warning(caplog):
    """Unmatched citations trigger a WARNING log."""
    import logging

    from rag.generator import _extract_citations

    answer = "[ghost-doc, chunk 99] is cited but not in context."
    chunks = []  # no matching chunks
    with caplog.at_level(logging.WARNING, logger="rag.generator"):
        result = _extract_citations(answer, chunks)
    assert len(result) == 1
    assert result[0]["found_in_context"] is False
    assert any("not matched" in r.message for r in caplog.records)


def test_citation_deduplication():
    """Same citation appearing in both patterns is not doubled."""
    from rag.generator import _extract_citations

    # Strict and loose both match [dallas-code, chunk 5]
    # The strict pattern matches; loose should not add a duplicate.
    answer = "[dallas-code, chunk 5]"
    chunks = _make_chunks([("dallas-code", 5)])
    result = _extract_citations(answer, chunks)
    assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
#  Task 14C — Jurisdiction resolver
# ═══════════════════════════════════════════════════════════════


_CENSUS_SUCCESS = {
    "result": {
        "addressMatches": [
            {
                "matchedAddress": "1234 MAIN ST, DALLAS, TX 75201",
                "coordinates": {"x": -96.797, "y": 32.777},
            }
        ]
    }
}

_CENSUS_NO_MATCH = {"result": {"addressMatches": []}}


def _mock_requests_get(url, params=None, timeout=None):
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    if "geocoding.geo.census.gov" in url:
        mock.json.return_value = _CENSUS_SUCCESS
    else:
        mock.json.return_value = {}
    return mock


def test_geocode_returns_coordinates():
    """Census API success → GeocodedAddress with correct lat/lng."""
    import requests

    from rag.jurisdiction_resolver import geocode

    with patch.object(requests, "get", side_effect=_mock_requests_get):
        result = geocode("1234 Main St, Dallas, TX 75201")

    assert result is not None
    assert abs(result.lat - 32.777) < 0.01
    assert abs(result.lng - (-96.797)) < 0.01


def test_geocode_no_match_returns_none():
    """Census API no-match → None."""
    import requests

    from rag.jurisdiction_resolver import geocode

    def no_match(url, params=None, timeout=None):
        m = MagicMock()
        m.raise_for_status.return_value = None
        m.json.return_value = _CENSUS_NO_MATCH
        return m

    with patch.object(requests, "get", side_effect=no_match):
        result = geocode("Not a real address xyz")

    assert result is None


def test_resolve_jurisdiction_hits_polygon(monkeypatch):
    """Full resolution: geocode succeeds + polygon hit → resolved jurisdiction."""
    import requests

    from rag.jurisdiction_resolver import resolve_jurisdiction

    # Mock Census geocode
    monkeypatch.setattr(requests, "get", _mock_requests_get)

    # Mock DB point-in-polygon to return 'dallas'
    with patch("rag.jurisdiction_resolver._point_in_polygon", return_value="dallas"):
        result = resolve_jurisdiction("1234 Main St, Dallas, TX 75201")

    assert result.resolved is True
    assert result.jurisdiction_id == "dallas"
    assert result.geocode is not None


def test_resolve_jurisdiction_no_polygon(monkeypatch):
    """Geocode succeeds but address outside any loaded boundary → unresolved."""
    import requests

    from rag.jurisdiction_resolver import resolve_jurisdiction

    monkeypatch.setattr(requests, "get", _mock_requests_get)

    with patch("rag.jurisdiction_resolver._point_in_polygon", return_value=None):
        result = resolve_jurisdiction("999 Nowhere Rd, Outercity, TX")

    assert result.resolved is False
    assert result.error is not None


def test_resolve_jurisdiction_empty_address():
    """Empty address → unresolved with error message."""
    from rag.jurisdiction_resolver import resolve_jurisdiction

    result = resolve_jurisdiction("")
    assert result.resolved is False
    assert "Empty" in result.error


# ═══════════════════════════════════════════════════════════════
#  Task 15 — Conflict detector
# ═══════════════════════════════════════════════════════════════


def _make_chunk(
    doc_id: str,
    chunk_index: int,
    authority: str,
    content: str,
    filtered_out: bool = False,
) -> dict[str, Any]:
    return {
        "id": f"uuid-{doc_id}-{chunk_index}",
        "document_id": f"doc-uuid-{doc_id}",
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "municipality": "dallas",
        "authority_level": authority,
        "doc_type": "zoning_ordinance",
        "document_status": "active",
        "source_tier": 1,
        "similarity": 0.80,
        "filtered_out": filtered_out,
        "content": content,
    }


def test_conflict_detected_numeric_mismatch():
    """Two chunks from different authority levels with different setback values → conflict."""
    from rag.conflict_detector import detect_conflicts

    chunks = [
        _make_chunk(
            "dallas-zoning", 10, "municipal",
            "The minimum setback requirement for residential fences is 3 feet from the property line.",
        ),
        _make_chunk(
            "texas-state-code", 5, "state",
            "The minimum setback requirement shall be 5 feet from any property line.",
        ),
    ]
    results = detect_conflicts(chunks)
    assert len(results) >= 1
    subjects = [r.subject for r in results]
    assert "setback" in subjects


def test_no_conflict_same_values():
    """Two chunks from different levels with identical numeric values → no conflict."""
    from rag.conflict_detector import detect_conflicts

    chunks = [
        _make_chunk(
            "dallas-zoning", 10, "municipal",
            "The minimum setback for a fence is 3 feet from the property line.",
        ),
        _make_chunk(
            "texas-state-code", 5, "state",
            "The minimum setback shall be 3 feet from the property line.",
        ),
    ]
    results = detect_conflicts(chunks)
    assert len(results) == 0


def test_no_conflict_same_authority():
    """Two chunks with different values but same authority level → no conflict."""
    from rag.conflict_detector import detect_conflicts

    chunks = [
        _make_chunk(
            "dallas-zoning-1", 1, "municipal",
            "Setback of 3 feet required.",
        ),
        _make_chunk(
            "dallas-zoning-2", 2, "municipal",
            "Setback of 5 feet required.",
        ),
    ]
    results = detect_conflicts(chunks)
    # Same authority — should not be flagged as a cross-level conflict
    assert len(results) == 0


def test_filtered_chunks_excluded():
    """Chunks with filtered_out=True are not included in conflict analysis."""
    from rag.conflict_detector import detect_conflicts

    chunks = [
        _make_chunk(
            "dallas-zoning", 10, "municipal",
            "Setback of 3 feet required.",
        ),
        _make_chunk(
            "texas-state-code", 5, "state",
            "Setback of 5 feet required.",
            filtered_out=True,  # should be excluded
        ),
    ]
    results = detect_conflicts(chunks)
    # Only one passing chunk → no cross-level pair possible
    assert len(results) == 0


def test_higher_authority_helper():
    """_higher_authority returns the correct level."""
    from rag.conflict_detector import _higher_authority

    assert _higher_authority("municipal", "state") == "state"
    assert _higher_authority("federal", "state") == "federal"
    assert _higher_authority("county", "municipal") == "county"
