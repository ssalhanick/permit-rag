"""
api/routes/marketplace.py — Contractor-facing project browse/filter + listing detail.
========================================================================================
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from api.contractor_auth import require_contractor_profile
from api.schemas import MarketplaceListingResponse, ProjectResponse
from commerce.materials_estimate import build_project_materials_estimate
from db import client as db_client

router = APIRouter(prefix="/marketplace", tags=["marketplace"])
Contractor = Annotated[dict, Depends(require_contractor_profile)]


@router.get("/projects", response_model=list[ProjectResponse])
def browse_projects(
    _contractor: Contractor,
    trade: str | None = Query(default=None, description="Filter by a work_types entry, e.g. Roofing"),
    municipality: str | None = Query(default=None),
) -> list[dict]:
    """Open projects a contractor can bid on, filterable by trade and municipality."""
    rows = db_client.list_marketplace_projects(trade=trade, municipality=municipality)
    return [dict(row) for row in rows]


@router.get("/projects/{project_id}", response_model=MarketplaceListingResponse)
def marketplace_listing_detail(project_id: UUID, _contractor: Contractor) -> dict:
    """Full listing detail for one open project — scope, room-scan summary, materials estimate.

    Contractors aren't project members, so this deliberately does not go
    through projects.py's membership-based _require_role; any biddable
    contractor may view any listing that is currently open. Non-open
    projects 404 rather than exposing a status, so listing ids can't be
    probed for projects the contractor was never meant to see.
    """
    project = db_client.get_project(project_id)
    if not project or project.get("marketplace_status") != "open":
        raise HTTPException(status_code=404, detail="Listing not found.")

    rows = db_client.list_linked_project_room_scans(project_id)
    active = next((r for r in rows if r.get("scan_type") == "room" and r.get("is_active")), None)
    if not active:
        active = next((r for r in rows if r.get("scan_type") == "room"), None)

    return {
        "project": dict(project),
        "room_scan_summary": active.get("derived") if active else None,
        "materials_estimate": build_project_materials_estimate(project),
    }
