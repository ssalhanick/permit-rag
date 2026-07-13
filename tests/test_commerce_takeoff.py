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


def test_estimate_quantity_tile_from_derived() -> None:
    """Tile takeoff should convert wall area to sq ft with waste."""
    qty = estimate_quantity(
        "tile",
        {"floor_area_sqm": 10},
        {"price_unit": "sq_ft"},
    )
    assert qty is not None
    assert qty["unit"] == "sq_ft"
    assert qty["value"] > 100


def test_estimate_line_total() -> None:
    """Line total should multiply qty by unit price."""
    total = estimate_line_total(
        {"value": 40, "unit": "sq_ft", "waste_factor": 0.1},
        {"price": 1.5, "price_unit": "sq_ft"},
    )
    assert total is not None
    assert total["low"] == 60.0
