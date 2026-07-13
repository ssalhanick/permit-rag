"""
commerce/takeoff.py — quantity estimates from scan derived metrics + product specs.
"""

from __future__ import annotations

from typing import Any

_SQFT_PER_SQM = 10.7639
_DEFAULT_WASTE = 0.1


def extract_zip_from_address(address: str | None) -> str | None:
    """
    Pull a 5-digit US zip code from a project address string.

    Args:
        address: Free-form address (may be None).

    Returns:
        Five-digit zip or None when not found.
    """
    if not address:
        return None
    import re

    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", address.strip())
    return match.group(1) if match else None


def estimate_quantity(
    overlay_type: str,
    room_derived: dict[str, Any] | None,
    product_ref: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Estimate material quantity from room derived metrics and product unit.

    Args:
        overlay_type: paint, tile, trim, or appliance.
        room_derived: Derived scan metrics (areas, wall lengths).
        product_ref: Resolved product with price_unit when available.

    Returns:
        qty_estimate dict or None when metrics are insufficient.
    """
    derived = room_derived or {}
    price_unit = (product_ref or {}).get("price_unit") or ""
    waste = _DEFAULT_WASTE

    if overlay_type in ("tile", "paint"):
        area_sqm = float(derived.get("floor_area_sqm") or 0)
        if area_sqm <= 0:
            return None
        area_sqft = area_sqm * _SQFT_PER_SQM * (1 + waste)
        unit = "sq_ft"
        if price_unit == "each" or overlay_type == "appliance":
            return {"value": 1, "unit": "each", "waste_factor": 0}
        return {
            "value": round(area_sqft, 1),
            "unit": unit,
            "waste_factor": waste,
        }

    if overlay_type == "trim":
        lengths = derived.get("wall_lengths_m") or []
        if not lengths:
            return None
        perimeter_m = sum(float(x) for x in lengths)
        perimeter_ft = perimeter_m * 3.28084 * (1 + waste)
        return {
            "value": round(perimeter_ft, 1),
            "unit": "linear_ft",
            "waste_factor": waste,
        }

    if overlay_type == "appliance":
        return {"value": 1, "unit": "each", "waste_factor": 0}

    return None


def estimate_line_total(
    qty_estimate: dict[str, Any] | None,
    product_ref: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Compute an estimated line total from quantity and unit price.

    Args:
        qty_estimate: Output from estimate_quantity.
        product_ref: Product with price and price_unit.

    Returns:
        Dict with low/high estimate or None.
    """
    if not qty_estimate or not product_ref:
        return None
    price = product_ref.get("price")
    if price is None:
        return None
    try:
        unit_price = float(price)
    except (TypeError, ValueError):
        return None
    qty = float(qty_estimate.get("value") or 0)
    total = round(unit_price * qty, 2)
    return {
        "low": total,
        "high": round(total * 1.15, 2),
        "currency": "USD",
    }
