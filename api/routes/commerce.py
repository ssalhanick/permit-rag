"""
api/routes/commerce.py — product search and materials estimate routes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.design_intent_helpers import check_image_cap, record_image_usage
from api.schemas import (
    MaterialsEstimateResponse,
    ProductSearchRequest,
    ProductSearchResponse,
    RoomPreviewImageRequest,
    RoomPreviewImageResponse,
)
from commerce.materials_estimate import build_project_materials_estimate
from commerce.room_image import generate_room_preview_image
from commerce.serpapi_client import search_home_depot
from db import client as db_client

router = APIRouter(prefix="/commerce", tags=["commerce"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.post("/room-preview-image", response_model=RoomPreviewImageResponse)
def room_preview_image(
    body: RoomPreviewImageRequest,
    current_user: CurrentUser,
) -> dict:
    """
    Generate a room redesign preview image for iPhone AR asset_url.

    Metered per user: this bills a paid image provider on every call. Mock
    results cost nothing, so they are not recorded and do not consume the cap.
    """
    check_image_cap(current_user["user_id"])
    result = generate_room_preview_image(
        utterance=body.utterance,
        overlays=body.overlays,
        room_label=body.room_label,
        source_image_b64=body.source_image_b64,
        tiling=body.tiling,
    )
    if not result.get("mock"):
        record_image_usage(current_user["user_id"], model=str(result.get("model", "unknown")))
    return result


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

    return build_project_materials_estimate(project)
