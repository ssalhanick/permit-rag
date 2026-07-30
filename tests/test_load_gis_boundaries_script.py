"""Unit tests for scripts/load_gis_boundaries.py helpers (no DB, no network)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.load_gis_boundaries import (
    _validate_address_against_geometry,
    parse_boundary_geometry,
)


def _square_feature(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {
        "type": "Feature",
        "properties": {},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
        },
    }


def test_parse_boundary_geometry_single_polygon_becomes_multipolygon() -> None:
    data = {"type": "FeatureCollection", "features": [_square_feature(0, 0, 1, 1)]}
    geometry = parse_boundary_geometry(data)
    assert geometry.geom_type == "MultiPolygon"
    assert geometry.area == pytest.approx(1.0)


def test_parse_boundary_geometry_unions_multiple_features() -> None:
    data = {
        "type": "FeatureCollection",
        "features": [_square_feature(0, 0, 1, 1), _square_feature(1, 0, 2, 1)],
    }
    geometry = parse_boundary_geometry(data)
    assert geometry.geom_type == "MultiPolygon"
    assert geometry.area == pytest.approx(2.0)


def test_parse_boundary_geometry_empty_features_raises() -> None:
    with pytest.raises(ValueError, match="no features"):
        parse_boundary_geometry({"type": "FeatureCollection", "features": []})


def test_parse_boundary_geometry_no_geometry_raises() -> None:
    data = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}}]}
    with pytest.raises(ValueError, match="geometry"):
        parse_boundary_geometry(data)


def _fake_geocode(lat: float, lng: float):
    from rag.jurisdiction_resolver import GeocodedAddress

    return GeocodedAddress(
        input_address="addr", matched_address="addr", lat=lat, lng=lng, latency_ms=1,
    )


@patch("rag.jurisdiction_resolver.geocode")
def test_validate_address_inside_boundary(mock_geocode) -> None:
    mock_geocode.return_value = _fake_geocode(lat=0.5, lng=0.5)
    geometry = parse_boundary_geometry(
        {"type": "FeatureCollection", "features": [_square_feature(0, 0, 1, 1)]}
    )
    assert _validate_address_against_geometry("123 In Bounds St", geometry) is True


@patch("rag.jurisdiction_resolver.geocode")
def test_validate_address_outside_boundary(mock_geocode) -> None:
    mock_geocode.return_value = _fake_geocode(lat=5.0, lng=5.0)
    geometry = parse_boundary_geometry(
        {"type": "FeatureCollection", "features": [_square_feature(0, 0, 1, 1)]}
    )
    assert _validate_address_against_geometry("999 Way Outside Rd", geometry) is False


@patch("rag.jurisdiction_resolver.geocode")
def test_validate_address_geocode_failure_does_not_raise(mock_geocode) -> None:
    mock_geocode.return_value = None
    geometry = parse_boundary_geometry(
        {"type": "FeatureCollection", "features": [_square_feature(0, 0, 1, 1)]}
    )
    assert _validate_address_against_geometry("unresolvable", geometry) is False
