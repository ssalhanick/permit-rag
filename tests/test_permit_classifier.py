"""
tests/test_permit_classifier.py — Unit tests for rag/permit_classifier.py (Sprint 3 / Task 11)

Tests cover:
    - _classify_keyword: single type, multi-type, empty input, no-match fallback
    - classify_permit_types: keyword-only mode (use_nli=False)
    - classify_permit_types: NLI unavailable fallback path
    - classify_permit_types: empty / whitespace input
    - classify_permit_types: returns sorted list
    - permit_type_label: known and unknown slugs
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag.permit_classifier import (
    PERMIT_TYPES,
    _classify_keyword,
    classify_permit_types,
    permit_type_label,
)


# ════════════════════════════════════════════════
#  _classify_keyword
# ════════════════════════════════════════════════


def test_keyword_building_match():
    result = _classify_keyword("I want to build a garage addition")
    assert "building" in result


def test_keyword_electrical_match():
    result = _classify_keyword("need a 200-amp electrical panel upgrade")
    assert "electrical" in result


def test_keyword_multi_match():
    result = _classify_keyword("detached garage with bathroom and 200-amp panel")
    assert "building" in result
    assert "plumbing" in result
    assert "electrical" in result


def test_keyword_empty_defaults_to_building():
    result = _classify_keyword("")
    assert result == ["building"]


def test_keyword_no_match_defaults_to_building():
    result = _classify_keyword("xyzzy quux frobnicate")
    assert result == ["building"]


def test_keyword_sign():
    result = _classify_keyword("install a monument sign for the new retail store")
    assert "sign" in result


def test_keyword_historic():
    result = _classify_keyword("renovation in a historic conservation district")
    assert "historic" in result


def test_keyword_tree():
    result = _classify_keyword("removing a protected heritage tree from the backyard")
    assert "tree" in result


def test_keyword_grading():
    result = _classify_keyword("retaining wall and grading on a sloped lot")
    assert "grading" in result


def test_keyword_zoning():
    result = _classify_keyword("request a variance for lot coverage setback")
    assert "zoning" in result


def test_keyword_mechanical():
    result = _classify_keyword("replacing the HVAC system and adding ductwork")
    assert "mechanical" in result


# ════════════════════════════════════════════════
#  classify_permit_types — keyword-only mode
# ════════════════════════════════════════════════


def test_classify_keyword_only_building():
    result = classify_permit_types("new single-family construction", use_nli=False)
    assert "building" in result
    assert result == sorted(result)


def test_classify_keyword_only_multi():
    result = classify_permit_types(
        "commercial remodel with electrical and plumbing work", use_nli=False
    )
    assert "building" in result
    assert "electrical" in result
    assert "plumbing" in result


def test_classify_returns_sorted():
    result = classify_permit_types(
        "plumbing and electrical work for a garage", use_nli=False
    )
    assert result == sorted(result)


def test_classify_empty_string():
    result = classify_permit_types("", use_nli=False)
    assert result == ["building"]


def test_classify_whitespace_only():
    result = classify_permit_types("   ", use_nli=False)
    assert result == ["building"]


# ════════════════════════════════════════════════
#  classify_permit_types — NLI fallback path
# ════════════════════════════════════════════════


@patch("rag.permit_classifier._load_nli_classifier", return_value=None)
def test_classify_nli_unavailable_falls_back_to_keywords(mock_load):
    """When NLI model is None (not installed), keyword rules must kick in."""
    result = classify_permit_types("new garage addition", use_nli=True)
    assert "building" in result
    mock_load.assert_called_once()


@patch("rag.permit_classifier._load_nli_classifier")
def test_classify_nli_raises_falls_back(mock_load):
    """If the NLI classifier throws at inference time, fall back gracefully."""
    mock_clf = MagicMock()
    mock_clf.side_effect = RuntimeError("CUDA OOM")
    mock_load.return_value = mock_clf

    result = classify_permit_types("electrical panel upgrade", use_nli=True)
    # Should not raise; should return at least ["electrical"] via keywords
    assert isinstance(result, list)
    assert len(result) >= 1


@patch("rag.permit_classifier._load_nli_classifier")
def test_classify_nli_returns_above_threshold(mock_load):
    """NLI result with high-confidence types should be returned."""
    mock_clf = MagicMock()
    mock_clf.return_value = {
        "labels": ["building", "electrical", "plumbing", "mechanical",
                   "zoning", "grading", "tree", "historic", "sign"],
        "scores": [0.92, 0.85, 0.78, 0.20, 0.10, 0.05, 0.03, 0.02, 0.01],
    }
    mock_load.return_value = mock_clf

    result = classify_permit_types(
        "detached garage with bathroom and panel", use_nli=True, threshold=0.5
    )
    assert "building" in result
    assert "electrical" in result
    assert "plumbing" in result
    assert "mechanical" not in result


@patch("rag.permit_classifier._load_nli_classifier")
def test_classify_nli_nothing_above_threshold_uses_keywords(mock_load):
    """If NLI finds nothing above threshold, keyword rules supplement."""
    mock_clf = MagicMock()
    mock_clf.return_value = {
        "labels": PERMIT_TYPES,
        "scores": [0.05] * len(PERMIT_TYPES),  # all below any threshold
    }
    mock_load.return_value = mock_clf

    result = classify_permit_types("garage construction", use_nli=True, threshold=0.5)
    assert "building" in result  # keyword fallback kicks in


# ════════════════════════════════════════════════
#  permit_type_label
# ════════════════════════════════════════════════


def test_permit_type_label_known():
    assert permit_type_label("electrical") == "Electrical"
    assert permit_type_label("mechanical") == "HVAC / Mechanical"
    assert permit_type_label("building") == "Building / Structural"


def test_permit_type_label_unknown_titlecases():
    assert permit_type_label("custom_type") == "Custom Type"


def test_permit_type_label_all_known_types():
    """Ensure every canonical PERMIT_TYPE has a human-readable label."""
    for pt in PERMIT_TYPES:
        label = permit_type_label(pt)
        assert label  # non-empty
        assert isinstance(label, str)
