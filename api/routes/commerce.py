"""
api/routes/commerce.py — product search and materials estimate routes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.schemas import (
    MaterialsEstimateResponse,
    ProductSearchRequest,
    ProductSearchResponse,
)
from commerce.product_resolver import resolve_products_for_overlays
from commerce.serpapi_client import search_home_depot
from commerce.takeoff import extract_zip_from_address
from db import client as db_client

router = APIRouter(prefix="/commerce", tags=["commerce"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/products/search", response_model=ProductSearchResponse)
def search_products(body: ProductSearchRequest, _current_user: CurrentUser) -> dict:
    """Search Home Depot products localized by zip code."""
    products = search_home_depot(body.query, zip_code=body.zip_code, limit=body.limit)
    return {
        "products": products,
        "zip_code": body.zip_code,
    }


@router.get(
    "/projects/{project_id}/materials-estimate",
    response_model=MaterialsEstimateResponse,
)
def project_materials_estimate(
    project_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """
    Build a materials estimate from the project's active room scan type hints.

    Uses mock/search products when no overlays are stored server-side.
    """
    role = db_client.get_project_role(project_id, current_user["user_id"])
    if not role:
        raise HTTPException(status_code=403, detail="Insufficient project privileges.")

    project = db_client.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    zip_code = extract_zip_from_address(project.get("address")) or "75034"
    rows = db_client.list_linked_project_room_scans(project_id)
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
