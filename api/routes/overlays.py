"""
api/routes/overlays.py — Historic/conservation-district and HOA petitions.
============================================================================
Phase 4 of the jurisdiction-accuracy work: lets a trusted end-user (a
project's own editor/owner — the same tier already gated for sharing a
document into a project, per docs/sprint9_users_projects.md) upload
documentation for a neighborhood-scale overlay (Swiss Ave-style historic
district, a conservation district, an HOA's own bylaws) at the project level,
petitioned with a coarse default boundary around the project's address. Staff
review and approve it — optionally refining the boundary — after which its
documents surface for ANY project whose address falls inside that boundary,
not just the one that petitioned it (see db.client.match_overlay_chunks).

Reuses api.routes.upload's existing chunk/embed background-processing helper
rather than duplicating it.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)

from api.auth import get_current_user, get_optional_current_user
from api.routes.admin import _require_admin_auth
from api.routes.projects import _require_role
from api.routes.upload import ALLOWED_EXTENSIONS, UPLOAD_DIR, _process_upload
from api.schemas import ApproveOverlayRequest, OverlayResponse
from db import client as db_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["overlays"])
CurrentUser = Annotated[dict, Depends(get_current_user)]

VALID_OVERLAY_TYPES = {"historic_district", "conservation_district", "hoa", "other"}

# overlay documents don't fit VALID_AUTHORITY_LEVELS cleanly (HOA bylaws aren't
# government authority), but the schema's authority_level enum has no "private"
# tier — "municipal" is the closest real fit for a sub-city geographic scope.
_OVERLAY_AUTHORITY_LEVEL = "municipal"
_OVERLAY_DOC_TYPE_BY_TYPE = {
    "historic_district": "zoning_ordinance",
    "conservation_district": "zoning_ordinance",
    "hoa": "other",
    "other": "other",
}


def _to_overlay_response(row: dict) -> OverlayResponse:
    return OverlayResponse(
        id=row["id"],
        name=row["name"],
        overlay_type=row["overlay_type"],
        jurisdiction_id=row.get("jurisdiction_id"),
        status=row["status"],
        petitioning_project_id=row.get("petitioning_project_id"),
        approved_by=row.get("approved_by"),
        approved_at=row.get("approved_at"),
        notes=row.get("notes"),
        created_at=row["created_at"],
    )


@router.post(
    "/projects/{project_id}/overlays",
    response_model=OverlayResponse,
    status_code=201,
    summary="Petition a historic/conservation-district or HOA overlay for this project's area",
)
async def petition_overlay(
    project_id: UUID,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The overlay's source document (PDF or HTML)."),
    name: str = Form(..., description="e.g. 'Swiss Avenue Historic District' or 'Oak Hollow HOA'."),
    overlay_type: str = Form(..., description="historic_district | conservation_district | hoa | other"),
    notes: str | None = Form(default=None),
) -> OverlayResponse:
    """
    Petition a new overlay, scoped to this project's own address.

    Requires the project to have latitude/longitude on file (set at kickoff or
    via address auto-resolve) — a petition needs a point to draw its default
    boundary around. The overlay starts in 'petitioned' status with a coarse
    circular buffer; a staff reviewer approves it (optionally refining the
    boundary) via PATCH /admin/overlays/{overlay_id}/approve.
    """
    _require_role(project_id, current_user["user_id"], {"owner", "editor"}, current_user)

    if overlay_type not in VALID_OVERLAY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid overlay_type. Choose from: {sorted(VALID_OVERLAY_TYPES)}",
        )

    project = db_client.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    latitude, longitude = project.get("latitude"), project.get("longitude")
    if latitude is None or longitude is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This project has no address/coordinates on file yet — set an "
                "address before petitioning an overlay for its area."
            ),
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    overlay = db_client.create_overlay_petition(
        name=name,
        overlay_type=overlay_type,
        jurisdiction_id=project.get("municipality"),
        petitioned_by=current_user["user_id"],
        petitioning_project_id=project_id,
        latitude=latitude,
        longitude=longitude,
        notes=notes,
    )

    doc_id = f"overlay-{overlay['id']}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{doc_id}{suffix}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc
    finally:
        await file.close()

    background_tasks.add_task(
        _process_upload,
        doc_id=doc_id,
        local_path=str(dest),
        source_url=f"file://{dest.resolve()}",
        municipality=project.get("municipality") or "unknown",
        authority_level=_OVERLAY_AUTHORITY_LEVEL,
        doc_type=_OVERLAY_DOC_TYPE_BY_TYPE[overlay_type],
        subject_tags=[overlay_type],
        source_tier=3,
        project_id=project_id,
        uploaded_by=current_user["user_id"],
        overlay_id=overlay["id"],
    )

    log.info(
        "Overlay petitioned: id=%s name=%r type=%s project_id=%s",
        overlay["id"], name, overlay_type, project_id,
    )
    return _to_overlay_response(overlay)


@router.get(
    "/admin/overlays/pending",
    response_model=list[OverlayResponse],
    summary="List overlay petitions awaiting staff review",
)
def list_pending_overlays(
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> list[OverlayResponse]:
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    rows = db_client.list_pending_overlay_petitions()
    return [_to_overlay_response(row) for row in rows]


@router.patch(
    "/admin/overlays/{overlay_id}/approve",
    response_model=OverlayResponse,
    summary="Approve a petitioned overlay, optionally refining its boundary",
)
def approve_overlay_admin(
    overlay_id: UUID,
    body: ApproveOverlayRequest,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> OverlayResponse:
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    approver_id = (current_user or {}).get("user_id")
    row = db_client.approve_overlay(
        overlay_id, approved_by=approver_id, geojson_polygon=body.geojson_polygon,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Overlay not found.")
    return _to_overlay_response(row)


@router.post(
    "/admin/overlays/{overlay_id}/reject",
    response_model=OverlayResponse,
    summary="Reject a petitioned overlay",
)
def reject_overlay_admin(
    overlay_id: UUID,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> OverlayResponse:
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    approver_id = (current_user or {}).get("user_id")
    row = db_client.reject_overlay(overlay_id, approved_by=approver_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Overlay not found.")
    return _to_overlay_response(row)
