"""
tests/test_jurisdiction_resolver.py — validate_jurisdiction_id.
"""

from __future__ import annotations

from unittest.mock import patch

from rag.jurisdiction_resolver import validate_jurisdiction_id


@patch("db.client.get_jurisdiction")
def test_validate_jurisdiction_id_canonicalizes_before_lookup(mock_get_jurisdiction) -> None:
    """A hyphenated Fort Worth spelling should be looked up as 'fortworth'."""
    mock_get_jurisdiction.return_value = {"id": "fortworth", "name": "City of Fort Worth"}

    candidate, error = validate_jurisdiction_id("fort-worth")

    assert candidate == "fortworth"
    assert error is None
    mock_get_jurisdiction.assert_called_once_with("fortworth")


@patch("db.client.get_jurisdiction")
def test_validate_jurisdiction_id_unknown_is_not_an_error(mock_get_jurisdiction) -> None:
    """An unrecognized jurisdiction is reported, not rejected as bad input."""
    mock_get_jurisdiction.return_value = None

    candidate, error = validate_jurisdiction_id("frisco")

    assert candidate is None
    assert error is not None
    assert "frisco" in error


def test_validate_jurisdiction_id_empty_input() -> None:
    candidate, error = validate_jurisdiction_id(None)
    assert candidate is None
    assert error == "no municipality provided"
