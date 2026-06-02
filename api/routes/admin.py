"""
api/routes/admin.py — Admin governance mutation endpoints
==========================================================
Provides document metadata update and supersession routes.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from api.schemas import (
    DocumentAdminActionResponse,
    DocumentAdminUpdateRequest,
    DocumentDetailResponse,
    DocumentSupersedeRequest,
    DocumentSummaryResponse,
    ErrorResponse,
)
from db import client as db_client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/documents", tags=["admin"])


def _require_admin_auth(x_admin_token: Optional[str], x_admin_role: Optional[str]) -> None:
    """Enforce token + role checks for admin routes when enabled."""
    required = os.environ.get("API_ADMIN_AUTH_REQUIRED", "true").strip().lower()
    auth_required = required in {"1", "true", "yes", "on"}
    if not auth_required:
        return

    configured_token = os.environ.get("API_ADMIN_TOKEN", "").strip()
    if not configured_token:
        raise HTTPException(
            status_code=503,
            detail="Admin auth is enabled but API_ADMIN_TOKEN is not configured.",
        )
    if x_admin_token != configured_token:
        raise HTTPException(status_code=403, detail="Invalid admin token.")

    raw_roles = os.environ.get("API_ADMIN_ALLOWED_ROLES", "admin")
    allowed_roles = {value.strip().lower() for value in raw_roles.split(",") if value.strip()}
    if allowed_roles:
        role = (x_admin_role or "").strip().lower()
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient admin role.")


def _to_document_summary(row: dict) -> DocumentSummaryResponse:
    """Convert a DB row into the shared document summary schema."""
    return DocumentSummaryResponse(
        id=row["id"],
        doc_id=row["doc_id"],
        source_url=row["source_url"],
        municipality=row["municipality"],
        authority_level=row["authority_level"],
        doc_type=row["doc_type"],
        subject_tags=row["subject_tags"],
        document_status=row["document_status"],
        is_current=row["is_current"],
        effective_date=row["effective_date"],
        review_due=row["review_due"],
        retrieval_weight=float(row["retrieval_weight"]),
        updated_at=row["updated_at"],
    )


def _to_document_detail(row: dict) -> DocumentDetailResponse:
    """Build detail schema with chunk count for an existing DB row."""
    chunk_count = db_client.count_chunks(row["id"])
    summary = _to_document_summary(row)
    return DocumentDetailResponse(
        **summary.model_dump(),
        checksum_sha256=row["checksum_sha256"],
        source_etag=row["source_etag"],
        local_path=row["local_path"],
        superseded_by=row["superseded_by"],
        ingested_at=row["ingested_at"],
        chunk_count=chunk_count,
    )


@router.patch(
    "/{doc_id}",
    response_model=DocumentAdminActionResponse,
    responses={
        403: {"model": ErrorResponse, "description": "Invalid admin token"},
        503: {"model": ErrorResponse, "description": "Admin auth misconfiguration"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        500: {"model": ErrorResponse, "description": "Admin update failure"},
    },
    summary="Update document governance metadata",
)
def patch_document_admin(
    doc_id: str,
    body: DocumentAdminUpdateRequest,
    x_admin_token: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
) -> DocumentAdminActionResponse:
    """Patch mutable governance fields for an existing document."""
    _require_admin_auth(x_admin_token, x_admin_role)
    try:
        updated = db_client.update_document_admin_fields(doc_id, **body.model_dump())
    except Exception as exc:
        log.exception("Admin patch failed for doc_id=%s", doc_id)
        raise HTTPException(status_code=500, detail=f"Admin patch error: {exc}") from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    detail = _to_document_detail(updated)
    return DocumentAdminActionResponse(
        action="update_document_metadata",
        message=f"Updated admin metadata for {doc_id}.",
        document=detail,
    )


@router.post(
    "/{doc_id}/supersede",
    response_model=DocumentAdminActionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid supersession request"},
        403: {"model": ErrorResponse, "description": "Invalid admin token"},
        503: {"model": ErrorResponse, "description": "Admin auth misconfiguration"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        500: {"model": ErrorResponse, "description": "Supersession failure"},
    },
    summary="Mark a document as superseded",
)
def supersede_document_admin(
    doc_id: str,
    body: DocumentSupersedeRequest,
    x_admin_token: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
) -> DocumentAdminActionResponse:
    """Supersede doc_id using replacement_doc_id and downweight old retrieval."""
    _require_admin_auth(x_admin_token, x_admin_role)
    try:
        updated = db_client.supersede_document(
            doc_id,
            body.replacement_doc_id,
            superseded_weight=body.superseded_weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("Supersede failed for doc_id=%s", doc_id)
        raise HTTPException(status_code=500, detail=f"Supersede error: {exc}") from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    detail = _to_document_detail(updated)
    return DocumentAdminActionResponse(
        action="supersede_document",
        message=f"Superseded {doc_id} with {body.replacement_doc_id}.",
        document=detail,
    )
