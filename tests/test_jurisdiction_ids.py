"""
tests/test_jurisdiction_ids.py — jurisdiction ID canonicalization.
"""

from __future__ import annotations

import pytest

from rag.jurisdiction_ids import canonicalize, slugify


@pytest.mark.parametrize(
    "raw",
    ["fort-worth", "fort worth", "Fort Worth", "FORT-WORTH", "ft-worth", "ft worth", "ftworth"],
)
def test_canonicalize_fort_worth_variants_converge(raw: str) -> None:
    """Every known Fort Worth spelling must converge on the corpus-canonical id."""
    assert canonicalize(raw) == "fortworth"


def test_canonicalize_ftworth_and_fortworth_are_not_confused() -> None:
    """Regression guard: 'ftworth' and 'fortworth' are genuinely different strings."""
    assert canonicalize("ftworth") == "fortworth"
    assert canonicalize("fortworth") == "fortworth"


def test_canonicalize_preserves_county_hyphen() -> None:
    """County ids intentionally carry a hyphen and must not be mangled."""
    assert canonicalize("dallas-county") == "dallas-county"
    assert canonicalize("Dallas County") == "dallas-county"


def test_canonicalize_bare_city_unchanged() -> None:
    assert canonicalize("Dallas") == "dallas"
    assert canonicalize("plano") == "plano"


def test_canonicalize_empty_or_none_returns_none() -> None:
    assert canonicalize(None) is None
    assert canonicalize("") is None
    assert canonicalize("   ") is None


def test_slugify_collapses_whitespace_but_keeps_hyphens() -> None:
    assert slugify("Fort   Worth") == "fort-worth"
    assert slugify("dallas-county") == "dallas-county"
