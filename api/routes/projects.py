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
    CreateProjectRequest,
    DocumentSummaryResponse,
    ProjectMemberResponse,
    ProjectResponse,
    ShareDocumentRequest,
    TransferOwnershipRequest,
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
    project = db_client.create_project(
        name=body.name,
        owner_user_id=current_user["user_id"],
        description=body.description,
        municipality=body.municipality,
    )
    return dict(project)


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
    body: CreateProjectRequest,
    current_user: CurrentUser,
) -> dict:
    """Update mutable project settings (owner only)."""
    _require_role(project_id, current_user["user_id"], {"owner"})
    updated = db_client.update_project(
        project_id,
        name=body.name,
        description=body.description,
        municipality=body.municipality,
    )
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
