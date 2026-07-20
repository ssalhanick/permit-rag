"""
api/routes/projects.py — Project lifecycle and membership management routes.
=============================================================================
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.schemas import (
    AddMemberRequest,
    AssetSyncAckRequest,
    AssetSyncAckResponse,
    CreateProjectRequest,
    DesignIntentRequest,
    DesignIntentResponse,
    DocumentSummaryResponse,
    LinkRoomScansRequest,
    ProjectLinkedRoomScanResponse,
    ProjectMemberResponse,
    ProjectResponse,
    RoomScanResponse,
    RoomSummaryRequest,
    ShareDocumentRequest,
    TransferOwnershipRequest,
    UpdateProjectRequest,
    UpsertRoomScansRequest,
    UserRoomScanResponse,
    KickoffChatRequest,
    KickoffChatResponse,
)
from db import client as db_client

router = APIRouter(prefix="/projects", tags=["projects"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _require_role(project_id: UUID, user_id: UUID, allowed: set[str]) -> None:
    """Raise HTTP 403 if user's project role is not in allowed set."""
    role = db_client.get_project_role(project_id, user_id)
    if not role or role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient project privileges.")


@router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(body: CreateProjectRequest, current_user: CurrentUser) -> dict:
    """Create a new project owned by the caller."""
    historic, conservation = None, None
    municipality = body.municipality
    latitude = body.latitude
    longitude = body.longitude

    if (latitude is None or longitude is None or municipality is None) and body.address:
        from rag.jurisdiction_resolver import resolve_jurisdiction
        try:
            res = resolve_jurisdiction(body.address)
            if res.municipality:
                municipality = res.municipality
            if res.geocode:
                latitude = res.geocode.lat
                longitude = res.geocode.lng
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("create_project: Failed to auto-resolve jurisdiction for %r: %s", body.address, e)

    if latitude is not None and longitude is not None:
        from rag.gis import lookup_jurisdiction_overlays
        historic, conservation = lookup_jurisdiction_overlays(
            municipality, latitude, longitude
        )

    project = db_client.create_project(
        name=body.name,
        owner_user_id=current_user["user_id"],
        description=body.description,
        municipality=municipality,
        address=body.address,
        latitude=latitude,
        longitude=longitude,
        historic_district=historic,
        conservation_district=conservation,
        spaces=body.spaces,
        work_types=body.work_types,
        materials=body.materials,
        recommended_permits=body.recommended_permits,
        budget=body.budget,
        persona=body.persona,
        custom_system_prompt=body.custom_system_prompt,
    )
    return dict(project)


@router.post("/kickoff/chat", response_model=KickoffChatResponse)
def kickoff_chat(body: KickoffChatRequest, current_user: CurrentUser) -> dict:
    """Drive the project kickoff dialog via Claude/Ollama."""
    from rag.generator import generate_kickoff_chat_response

    history_dicts = [{"role": msg.role, "content": msg.content} for msg in body.history]
    try:
        res = generate_kickoff_chat_response(
            history_dicts,
            address=body.address,
            municipality=body.municipality,
            spaces=body.spaces,
            work_types=body.work_types,
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM Chat Error: {exc}") from exc


@router.get("/", response_model=list[ProjectResponse])
def list_projects(current_user: CurrentUser) -> list[dict]:
    """List all projects the caller is a member of."""
    projects = db_client.list_projects_for_user(current_user["user_id"])
    return [dict(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, current_user: CurrentUser) -> dict:
    """Fetch details of a single project."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    project = db_client.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    return dict(project)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    current_user: CurrentUser,
) -> dict:
    """Update mutable project settings and kickoff wizard fields."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})

    update_fields = body.model_dump(exclude_unset=True)

    db_params = {}
    for field in [
        "name", "description", "municipality", "address", "spaces",
        "work_types", "recommended_permits", "budget", "persona", "custom_system_prompt"
    ]:
        if field in update_fields:
            db_params[field] = update_fields[field]

    if "latitude" in update_fields or "longitude" in update_fields:
        lat = update_fields.get("latitude")
        lng = update_fields.get("longitude")
        db_params["latitude"] = lat
        db_params["longitude"] = lng

        if lat is not None and lng is not None:
            from rag.gis import lookup_jurisdiction_overlays
            munic = update_fields.get("municipality")
            if munic is None:
                current_project = db_client.get_project(project_id)
                munic = current_project.get("municipality") if current_project else None

            historic, conservation = lookup_jurisdiction_overlays(munic, lat, lng)
            db_params["historic_district"] = historic
            db_params["conservation_district"] = conservation
        else:
            db_params["historic_district"] = None
            db_params["conservation_district"] = None

    updated = db_client.update_project(project_id, **db_params)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return dict(updated)


@router.delete("/{project_id}", status_code=200)
def archive_project(project_id: UUID, current_user: CurrentUser) -> dict:
    """Archive a project (owner only)."""
    _require_role(project_id, current_user["user_id"], {"owner"})
    if not db_client.archive_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"detail": "Project archived successfully."}


@router.post("/{project_id}/transfer", response_model=ProjectResponse)
def transfer_ownership(
    project_id: UUID,
    body: TransferOwnershipRequest,
    current_user: CurrentUser,
) -> dict:
    """Transfer project ownership (owner only)."""
    _require_role(project_id, current_user["user_id"], {"owner"})
    updated = db_client.transfer_project_ownership(project_id, body.new_owner_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return dict(updated)


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
def list_members(project_id: UUID, current_user: CurrentUser) -> list[dict]:
    """List all members of the project."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    members = db_client.list_project_members(project_id)
    return [dict(m) for m in members]


@router.post("/{project_id}/members", status_code=201)
def add_member(
    project_id: UUID,
    body: AddMemberRequest,
    current_user: CurrentUser,
) -> dict:
    """Add or invite a user to the project (owner only)."""
    _require_role(project_id, current_user["user_id"], {"owner"})
    if not db_client.get_user_by_id(body.user_id):
        raise HTTPException(status_code=404, detail="User not found.")
    row = db_client.upsert_project_member(project_id, body.user_id, role=body.role)
    return dict(row)


@router.patch("/{project_id}/members/{user_id}", status_code=200)
def change_member_role(
    project_id: UUID,
    user_id: UUID,
    body: AddMemberRequest,
    current_user: CurrentUser,
) -> dict:
    """Modify role of a member (owner only)."""
    _require_role(project_id, current_user["user_id"], {"owner"})
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot modify your own owner role.")
    row = db_client.upsert_project_member(project_id, user_id, role=body.role)
    return dict(row)


@router.delete("/{project_id}/members/{user_id}", status_code=200)
def remove_member(
    project_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """Remove a member from the project (owner only)."""
    _require_role(project_id, current_user["user_id"], {"owner"})
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="Owner cannot be removed. Transfer ownership first.")
    if not db_client.remove_project_member(project_id, user_id):
        raise HTTPException(status_code=404, detail="Member not found.")
    return {"detail": "Member removed."}


@router.get("/{project_id}/documents", response_model=list[DocumentSummaryResponse])
def list_shared_documents(project_id: UUID, current_user: CurrentUser) -> list[dict]:
    """List all documents shared to this project."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    docs = db_client.list_project_documents(project_id)
    return [dict(d) for d in docs]


@router.post("/{project_id}/documents", status_code=201)
def share_document(
    project_id: UUID,
    body: ShareDocumentRequest,
    current_user: CurrentUser,
) -> dict:
    """Share a document to the project (owner/editor only)."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    if not db_client.get_document_by_uuid(body.document_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    row = db_client.share_document_to_project(
        project_id=project_id,
        document_id=body.document_id,
        added_by=current_user["user_id"],
    )
    return dict(row)


@router.delete("/{project_id}/documents/{document_id}", status_code=200)
def unshare_document(
    project_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """Remove a document from the project (owner/editor only)."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    if not db_client.unshare_document_from_project(project_id, document_id):
        raise HTTPException(status_code=404, detail="Document was not shared to this project.")
    return {"detail": "Document unshared."}


@router.post("/{project_id}/assets/sync-ack", response_model=AssetSyncAckResponse)
def asset_sync_ack(
    project_id: UUID,
    body: AssetSyncAckRequest,
    current_user: CurrentUser,
) -> dict:
    """Acknowledge mobile asset upload for lifecycle eviction gate."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    if body.doc_id and not db_client.get_document_by_doc_id(body.doc_id):
        raise HTTPException(status_code=404, detail="Document not found for sync ack.")
    return {
        "asset_id": body.asset_id,
        "checksum_sha256": body.checksum_sha256,
        "sync_state": "cloud_primary",
    }


@router.patch("/{project_id}/room-summary", response_model=ProjectResponse)
def update_room_summary(
    project_id: UUID,
    body: RoomSummaryRequest,
    current_user: CurrentUser,
) -> dict:
    """Persist derived room capture summary (no raw mesh). Deprecated — prefer room-scans."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    updated = db_client.update_project(
        project_id,
        room_summary=body.room_summary,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found.")
    return dict(updated)


@router.get("/{project_id}/room-scans", response_model=list[ProjectLinkedRoomScanResponse])
def list_room_scans(project_id: UUID, current_user: CurrentUser) -> list[dict]:
    """List library scans linked to this project."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    rows = db_client.list_linked_project_room_scans(project_id)
    return [dict(row) for row in rows]


@router.post("/{project_id}/room-scans", response_model=list[ProjectLinkedRoomScanResponse])
def upsert_room_scans(
    project_id: UUID,
    body: UpsertRoomScansRequest,
    current_user: CurrentUser,
) -> list[dict]:
    """Upsert user library scans and link them to the project."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    for scan in body.scans:
        if "surfaces" in (scan.derived or {}):
            raise HTTPException(
                status_code=422,
                detail="Derived summaries must not include surfaces.",
            )
    payload = [scan.model_dump() for scan in body.scans]
    db_client.upsert_user_room_scans(current_user["user_id"], payload)
    db_client.upsert_project_room_scans(project_id, payload)
    scan_ids = [scan["id"] for scan in payload]
    active = next((s["id"] for s in payload if s.get("is_active")), None)
    rows = db_client.link_scans_to_project(
        project_id,
        current_user["user_id"],
        scan_ids,
        active_scan_id=active,
    )
    return [dict(row) for row in rows]


@router.post("/{project_id}/room-scans/link", response_model=list[ProjectLinkedRoomScanResponse])
def link_room_scans(
    project_id: UUID,
    body: LinkRoomScansRequest,
    current_user: CurrentUser,
) -> list[dict]:
    """Attach existing library scans to a project."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    try:
        rows = db_client.link_scans_to_project(
            project_id,
            current_user["user_id"],
            body.scan_ids,
            active_scan_id=body.active_scan_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [dict(row) for row in rows]


@router.delete("/{project_id}/room-scans/{scan_id}", status_code=200)
def unlink_room_scan(
    project_id: UUID,
    scan_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """Remove a scan from the project (keeps it in the user's library)."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    if not db_client.unlink_scan_from_project(project_id, scan_id):
        raise HTTPException(status_code=404, detail="Scan link not found.")
    return {"detail": "Scan unlinked from project."}


@router.patch("/{project_id}/room-scans/{scan_id}/active", response_model=ProjectLinkedRoomScanResponse)
def set_active_room_scan(
    project_id: UUID,
    scan_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """Set the active room scan used for chat context."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor"})
    updated = db_client.set_active_room_scan(project_id, scan_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Room scan not found.")
    rows = db_client.list_linked_project_room_scans(project_id)
    match = next((r for r in rows if r["id"] == scan_id), updated)
    return dict(match)


@router.post(
    "/{project_id}/room-scans/{scan_id}/design-intent",
    response_model=DesignIntentResponse,
)
def room_design_intent_by_scan(
    project_id: UUID,
    scan_id: UUID,
    body: DesignIntentRequest,
    current_user: CurrentUser,
) -> dict:
    """Parse remodel intent for a linked room scan (standalone or structure child)."""
    from api.design_intent_helpers import _resolve_room_scan_row, run_design_intent

    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    rows = db_client.list_linked_project_room_scans(project_id)
    room_row = _resolve_room_scan_row(rows, scan_id)
    return run_design_intent(
        user_id=current_user["user_id"],
        project_id=project_id,
        scan_id=scan_id,
        room_row=room_row,
        body=body,
    )


@router.post(
    "/{project_id}/room-scans/{structure_id}/rooms/{room_id}/design-intent",
    response_model=DesignIntentResponse,
)
def room_design_intent(
    project_id: UUID,
    structure_id: UUID,
    room_id: UUID,
    body: DesignIntentRequest,
    current_user: CurrentUser,
) -> dict:
    """Legacy nested route — delegates to scan_id resolver."""
    _require_role(project_id, current_user["user_id"], {"owner", "editor", "viewer"})
    rows = db_client.list_linked_project_room_scans(project_id)
    room_row = next((r for r in rows if r["id"] == room_id), None)
    if not room_row or room_row.get("scan_type") != "room":
        raise HTTPException(status_code=404, detail="Room scan not found.")
    parent = room_row.get("parent_scan_id")
    if parent is not None and parent != structure_id:
        raise HTTPException(status_code=404, detail="Room does not belong to structure.")
    if parent is None and structure_id != room_id:
        raise HTTPException(status_code=404, detail="Room does not belong to structure.")

    from api.design_intent_helpers import run_design_intent

    return run_design_intent(
        user_id=current_user["user_id"],
        project_id=project_id,
        scan_id=room_id,
        room_row=room_row,
        body=body,
    )
