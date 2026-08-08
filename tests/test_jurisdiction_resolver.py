"""
tests/test_jurisdiction_resolver.py — validate_jurisdiction_id and the
nationwide Census `geographies` fallback (resolve_jurisdiction_for_point,
_geographies_for_point, _resolve_via_geographies).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import rag.jurisdiction_resolver as jurisdiction_resolver
from rag.jurisdiction_resolver import (
    GeographyMatch,
    _geography_cache,
    resolve_jurisdiction_for_point,
    validate_jurisdiction_id,
)


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


# ═══════════════════════════════════════════════════════════════
#  Nationwide fallback — _geographies_for_point
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _clear_geography_cache():
    """The geographies cache is process-global; isolate tests from each other."""
    _geography_cache.clear()
    yield
    _geography_cache.clear()


def _census_geographies_body(*, place=None, county=None, state=None) -> dict:
    """Build a Census `geographies` response shape for the given layers."""
    geographies: dict = {}
    if place is not None:
        geographies["Incorporated Places"] = [place]
    if county is not None:
        geographies["Counties"] = [county]
    if state is not None:
        geographies["States"] = [state]
    return {"result": {"geographies": geographies}}


@patch("rag.jurisdiction_resolver._census_get")
def test_geographies_for_point_incorporated_place_hit(mock_census_get) -> None:
    mock_census_get.return_value = _census_geographies_body(
        place={"BASENAME": "Dallas", "NAME": "Dallas city"},
        county={"BASENAME": "Dallas", "NAME": "Dallas County"},
        state={"NAME": "Texas", "STUSAB": "TX"},
    )

    result = jurisdiction_resolver._geographies_for_point(32.776661, -96.795837)

    assert result.place_name == "Dallas"
    assert result.county_name == "Dallas County"
    assert result.state_name == "Texas"


@patch("rag.jurisdiction_resolver._census_get")
def test_geographies_for_point_unincorporated_county_only(mock_census_get) -> None:
    """No incorporated place layer -> place_name is None, county/state still resolve."""
    mock_census_get.return_value = _census_geographies_body(
        county={"BASENAME": "Loving", "NAME": "Loving County"},
        state={"NAME": "Texas", "STUSAB": "TX"},
    )

    result = jurisdiction_resolver._geographies_for_point(31.85, -103.58)

    assert result.place_name is None
    assert result.county_name == "Loving County"
    assert result.state_name == "Texas"


@patch("rag.jurisdiction_resolver._census_get")
def test_geographies_for_point_outside_us_all_none(mock_census_get) -> None:
    mock_census_get.return_value = _census_geographies_body()

    result = jurisdiction_resolver._geographies_for_point(48.85, 2.35)  # Paris

    assert result.place_name is None
    assert result.county_name is None
    assert result.state_name is None


@patch("rag.jurisdiction_resolver._census_get")
def test_geographies_for_point_request_failure_returns_none(mock_census_get) -> None:
    mock_census_get.return_value = None  # every retry failed

    result = jurisdiction_resolver._geographies_for_point(32.776661, -96.795837)

    assert result is None


@patch("rag.jurisdiction_resolver._census_get")
def test_geographies_for_point_caches_repeat_lookups(mock_census_get) -> None:
    mock_census_get.return_value = _census_geographies_body(
        place={"BASENAME": "Plano"}, county={"NAME": "Collin County"},
        state={"NAME": "Texas", "STUSAB": "TX"},
    )

    first = jurisdiction_resolver._geographies_for_point(33.02, -96.70)
    second = jurisdiction_resolver._geographies_for_point(33.02, -96.70)

    assert first == second
    mock_census_get.assert_called_once()


@patch("rag.jurisdiction_resolver._census_get")
def test_geographies_for_point_does_not_cache_failures(mock_census_get) -> None:
    mock_census_get.return_value = None

    jurisdiction_resolver._geographies_for_point(33.02, -96.70)
    jurisdiction_resolver._geographies_for_point(33.02, -96.70)

    assert mock_census_get.call_count == 2


# ═══════════════════════════════════════════════════════════════
#  Nationwide fallback — _resolve_via_geographies
# ═══════════════════════════════════════════════════════════════


@patch("db.client.upsert_jurisdiction")
@patch("db.client.get_jurisdiction")
@patch("rag.jurisdiction_resolver._geographies_for_point")
def test_resolve_via_geographies_creates_new_city_and_county(
    mock_geo, mock_get_jurisdiction, mock_upsert,
) -> None:
    """A city with no existing row gets a state-suffixed id and both its
    county and city rows lazily created, city's parent pointing at the county."""
    mock_geo.return_value = GeographyMatch(
        place_name="Springfield", county_name="Sangamon County",
        state_name="Illinois", latency_ms=50,
    )
    mock_get_jurisdiction.return_value = None  # nothing exists yet

    result = jurisdiction_resolver._resolve_via_geographies(39.78, -89.65)

    assert result == "springfield-illinois"
    county_call = next(
        c for c in mock_upsert.call_args_list if c.kwargs["id"] == "sangamon-county-illinois"
    )
    assert county_call.kwargs["parent_id"] == "illinois"
    assert county_call.kwargs["level"] == "county"
    city_call = next(
        c for c in mock_upsert.call_args_list if c.kwargs["id"] == "springfield-illinois"
    )
    assert city_call.kwargs["parent_id"] == "sangamon-county-illinois"
    assert city_call.kwargs["level"] == "city"


@patch("db.client.upsert_jurisdiction")
@patch("db.client.get_jurisdiction")
@patch("rag.jurisdiction_resolver._geographies_for_point")
def test_resolve_via_geographies_dfw_converges_on_existing_ids_without_upsert(
    mock_geo, mock_get_jurisdiction, mock_upsert,
) -> None:
    """Dallas resolves through KNOWN_ALIASES to the legacy unsuffixed id, and
    since that jurisdiction already exists, no new row is created."""
    mock_geo.return_value = GeographyMatch(
        place_name="Dallas", county_name="Dallas County",
        state_name="Texas", latency_ms=50,
    )
    mock_get_jurisdiction.return_value = {"id": "dallas"}  # already exists

    result = jurisdiction_resolver._resolve_via_geographies(32.776661, -96.795837)

    assert result == "dallas"
    mock_upsert.assert_not_called()


@patch("db.client.upsert_jurisdiction")
@patch("db.client.get_jurisdiction")
@patch("rag.jurisdiction_resolver._geographies_for_point")
def test_resolve_via_geographies_unincorporated_falls_back_to_county(
    mock_geo, mock_get_jurisdiction, mock_upsert,
) -> None:
    """No incorporated place in the Census response -> resolves to the county,
    not a failure — a correctness improvement over the old total-miss behavior."""
    mock_geo.return_value = GeographyMatch(
        place_name=None, county_name="Loving County",
        state_name="Texas", latency_ms=50,
    )
    mock_get_jurisdiction.return_value = None

    result = jurisdiction_resolver._resolve_via_geographies(31.85, -103.58)

    assert result == "loving-county-texas"


@patch("rag.jurisdiction_resolver._geographies_for_point")
def test_resolve_via_geographies_outside_us_returns_none(mock_geo) -> None:
    mock_geo.return_value = GeographyMatch(
        place_name=None, county_name=None, state_name=None, latency_ms=50,
    )

    assert jurisdiction_resolver._resolve_via_geographies(48.85, 2.35) is None


@patch("rag.jurisdiction_resolver._geographies_for_point")
def test_resolve_via_geographies_request_failure_returns_none(mock_geo) -> None:
    mock_geo.return_value = None

    assert jurisdiction_resolver._resolve_via_geographies(32.78, -96.80) is None


# ═══════════════════════════════════════════════════════════════
#  resolve_jurisdiction_for_point — override table then nationwide fallback
# ═══════════════════════════════════════════════════════════════


@patch("rag.jurisdiction_resolver._resolve_via_geographies")
@patch("rag.jurisdiction_resolver._point_in_polygon")
def test_resolve_jurisdiction_for_point_prefers_override_table(
    mock_point_in_polygon, mock_geographies,
) -> None:
    mock_point_in_polygon.return_value = "dallas"

    result = resolve_jurisdiction_for_point(32.78, -96.80)

    assert result == "dallas"
    mock_geographies.assert_not_called()


@patch("rag.jurisdiction_resolver._resolve_via_geographies")
@patch("rag.jurisdiction_resolver._point_in_polygon")
def test_resolve_jurisdiction_for_point_falls_back_to_nationwide(
    mock_point_in_polygon, mock_geographies,
) -> None:
    mock_point_in_polygon.return_value = None
    mock_geographies.return_value = "springfield-illinois"

    result = resolve_jurisdiction_for_point(39.78, -89.65)

    assert result == "springfield-illinois"
    mock_geographies.assert_called_once_with(39.78, -89.65)
