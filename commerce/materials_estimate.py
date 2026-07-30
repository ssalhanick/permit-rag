"""
commerce/materials_estimate.py — Shared materials-estimate builder.

Extracted from api/routes/commerce.py so both the homeowner-facing
GET /commerce/projects/{id}/materials-estimate route and the contractor-facing
marketplace listing detail route (api/routes/marketplace.py) can produce the
same estimate from the same project row, without one route module importing
another's handler function.
"""

from __future__ import annotations

from typing import Any

from commerce.product_resolver import resolve_products_for_overlays
from commerce.takeoff import extract_zip_from_address
from db import client as db_client


def build_project_materials_estimate(project: dict[str, Any]) -> dict[str, Any]:
    """Build a materials estimate from a project's active room scan, if any.

    Uses mock/search products when no overlays are stored server-side. Returns
    empty lines (not an error) when the project has no room scan yet.
    """
    zip_code = extract_zip_from_address(project.get("address")) or "75034"
    rows = db_client.list_linked_project_room_scans(project["id"])
    active = next((r for r in rows if r.get("scan_type") == "room" and r.get("is_active")), None)
    if not active:
        active = next((r for r in rows if r.get("scan_type") == "room"), None)

    if not active:
        return {"lines": [], "total_low": None, "total_high": None}

    base_overlay = {
        "surface_id": None,
        "type": "tile",
        "material_id": "white_subway_tile",
        "color_hex": "#F8F8F8",
        "asset_url": None,
    }
    enriched, _ = resolve_products_for_overlays(
        [base_overlay],
        room_derived=active.get("derived"),
        zip_code=zip_code,
        utterance="white subway tile",
    )

    lines = []
    total_low = 0.0
    total_high = 0.0
    for row in enriched:
        line_est = row.get("line_estimate") or {}
        low = line_est.get("low")
        high = line_est.get("high")
        if low is not None:
            total_low += float(low)
        if high is not None:
            total_high += float(high)
        lines.append(
            {
                "overlay_type": row.get("type") or "paint",
                "product_title": (row.get("product_ref") or {}).get("title"),
                "qty_estimate": row.get("qty_estimate"),
                "line_estimate": row.get("line_estimate"),
                "product_ref": row.get("product_ref"),
            }
        )

    return {
        "lines": lines,
        "total_low": round(total_low, 2) if lines else None,
        "total_high": round(total_high, 2) if lines else None,
    }
