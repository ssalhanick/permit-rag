"""
commerce/product_resolver.py — map design overlays to real retailer SKUs.
"""

from __future__ import annotations

from typing import Any

from commerce.serpapi_client import search_home_depot
from commerce.takeoff import estimate_line_total, estimate_quantity

_CATEGORY_QUERIES: dict[str, str] = {
    "subway_tile": "white subway tile 3x6 ceramic wall",
    "hex_tile": "gray hex tile floor",
    "interior_paint": "interior paint gallon",
    "baseboard_trim": "primed baseboard trim",
    "refrigerator": "stainless steel refrigerator",
}


def build_product_search(overlay: dict[str, Any], utterance: str = "") -> dict[str, Any]:
    """
    Build product_search attributes from an overlay patch.

    Args:
        overlay: Overlay with type and material_id.
        utterance: Original user instruction for query hints.

    Returns:
        product_search dict with category, attributes, and query string.
    """
    overlay_type = overlay.get("type") or "paint"
    material_id = overlay.get("material_id") or "generic_paint"
    attributes: dict[str, str] = {}

    if overlay_type == "tile":
        category = "subway_tile" if "subway" in material_id else "hex_tile"
        attributes["color"] = "white" if "white" in material_id else "gray"
        attributes["size"] = "3x6" if category == "subway_tile" else "hex"
    elif overlay_type == "trim":
        category = "baseboard_trim"
        attributes["color"] = "white"
    elif overlay_type == "appliance":
        category = "refrigerator"
        attributes["finish"] = "stainless"
    else:
        category = "interior_paint"
        attributes["color"] = "white"

    query = _CATEGORY_QUERIES.get(category, utterance or category.replace("_", " "))
    if utterance and len(utterance) > 5:
        query = utterance

    return {
        "product_category": category,
        "attributes": attributes,
        "query": query.strip(),
    }


def resolve_products_for_overlays(
    overlays: list[dict[str, Any]],
    *,
    room_derived: dict[str, Any] | None = None,
    zip_code: str = "75034",
    utterance: str = "",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Enrich overlays with product_ref, alternates, and qty_estimate.

    Args:
        overlays: Base overlay patches from design intent.
        room_derived: Room derived metrics for takeoff.
        zip_code: Zip for localized Home Depot search.
        utterance: Original remodel instruction.

    Returns:
        Tuple of (enriched overlays, flat product_candidates list).
    """
    enriched: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []

    for overlay in overlays:
        row = dict(overlay)
        product_search = row.get("product_search") or build_product_search(row, utterance)
        row["product_search"] = product_search

        candidates = search_home_depot(
            product_search["query"],
            zip_code=zip_code,
            limit=3,
        )
        all_candidates.extend(candidates)

        if candidates:
            row["product_ref"] = candidates[0]
            row["product_alternates"] = candidates[1:]
        else:
            row["product_ref"] = None
            row["product_alternates"] = []

        qty = estimate_quantity(
            row.get("type") or "paint",
            room_derived,
            row.get("product_ref"),
        )
        if qty:
            row["qty_estimate"] = qty
            line = estimate_line_total(qty, row.get("product_ref"))
            if line:
                row["line_estimate"] = line

        enriched.append(row)

    return enriched, all_candidates
