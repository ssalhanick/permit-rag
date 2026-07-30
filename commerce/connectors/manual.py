"""
commerce/connectors/manual.py — the generic materials fallback for any store
without a real connector.

Not a MaterialsConnector (commerce/connectors/base.py) — there is nothing to
search when a contractor's preferred store isn't integrated. This instead
validates and normalizes what the contractor typed directly (a store name,
product description, and price) into the same ProductRef shape a real
connector would have returned, so the rest of the bid pipeline (evaluator,
comparison UI) doesn't need to special-case a manually-sourced bid.

This is what actually satisfies "contractors are never limited to only
stores with a built connector" — real trade-account connectors (Home Depot
Pro, Lowe's Pro) are the deferred extension point, not this. This is
genuinely buildable now: no external dependency, no credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def build_manual_product_ref(
    description: str,
    price: float,
    *,
    store_name: str | None = None,
    unit: str = "each",
) -> dict[str, Any]:
    """Normalize a contractor-typed materials entry into a ProductRef-shaped dict."""
    description = description.strip()
    if not description:
        raise ValueError("description is required for a manual materials entry")
    if price < 0:
        raise ValueError("price cannot be negative")
    return {
        "retailer": "manual",
        "item_id": None,
        "sku": None,
        "title": description,
        "price": round(float(price), 2),
        "price_unit": unit,
        "image_url": None,
        "product_url": None,
        "store_id": store_name,
        "in_stock": None,
        "pickup_available": None,
        "price_as_of": datetime.now(UTC).isoformat(),
        "zip_code": None,
    }
