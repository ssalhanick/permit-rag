"""
tests/test_commerce_takeoff.py — quantity takeoff and zip extraction.
"""

from __future__ import annotations

from commerce.takeoff import (
    estimate_line_total,
    estimate_quantity,
    extract_zip_from_address,
)


def test_extract_zip_from_address() -> None:
    """Address parser should find a 5-digit zip."""
    assert extract_zip_from_address("123 Main St, Frisco, TX 75034") == "75034"
    assert extract_zip_from_address("no zip here") is None


def test_estimate_quantity_tile_uses_floor_area() -> None:
    """Tile covers the floor, so it must take floor area, not wall area."""
    qty = estimate_quantity(
        "tile",
        {"floor_area_sqm": 10, "wall_area_sqm": 33.6},
        {"price_unit": "sq_ft"},
    )
    assert qty is not None
    assert qty["unit"] == "sq_ft"
    # 10 m² -> 107.6 sq ft, +10% waste
    assert qty["value"] == 118.4


def test_estimate_quantity_paint_uses_wall_area() -> None:
    """Paint covers walls, so it must take wall area, not floor area."""
    qty = estimate_quantity(
        "paint",
        {"floor_area_sqm": 10, "wall_area_sqm": 33.6},
        {"price_unit": "sq_ft"},
    )
    assert qty is not None
    # 33.6 m² -> 361.7 sq ft, +10% waste
    assert qty["value"] == 397.8


def test_estimate_quantity_legacy_derived_keeps_prior_behavior() -> None:
    """
    Scans synced before the areas were split have no wall_area_sqm.

    Those stored wall area under floor_area_sqm, so both types fall back to it
    rather than existing projects losing their estimates.
    """
    legacy = {"floor_area_sqm": 10}
    tile = estimate_quantity("tile", legacy, {"price_unit": "sq_ft"})
    paint = estimate_quantity("paint", legacy, {"price_unit": "sq_ft"})
    assert tile is not None and paint is not None
    assert tile["value"] == paint["value"] == 118.4


def test_estimate_quantity_returns_none_without_floor_area() -> None:
    """A null floor area (no floor surface captured) must not estimate tile."""
    qty = estimate_quantity(
        "tile",
        {"floor_area_sqm": None, "wall_area_sqm": 33.6},
        {"price_unit": "sq_ft"},
    )
    assert qty is None


def test_estimate_line_total() -> None:
    """Line total should multiply qty by unit price."""
    total = estimate_line_total(
        {"value": 40, "unit": "sq_ft", "waste_factor": 0.1},
        {"price": 1.5, "price_unit": "sq_ft"},
    )
    assert total is not None
    assert total["low"] == 60.0
