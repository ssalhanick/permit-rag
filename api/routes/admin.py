"""
api/routes/admin.py — Admin governance mutation endpoints
==========================================================
Provides document metadata update and supersession routes.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
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


def _parse_role_set(env_key: str, default: str) -> set[str]:
    """Parse comma-separated role env var into normalized role set."""
    raw = os.environ.get(env_key, default)
    return {value.strip().lower() for value in raw.split(",") if value.strip()}


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

    allowed_roles = _parse_role_set("API_ADMIN_ALLOWED_ROLES", "admin")
    if allowed_roles:
        role = (x_admin_role or "").strip().lower()
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient admin role.")


def _require_any_tier_purge_role(x_admin_role: Optional[str]) -> None:
    """Require elevated role for purging non-project (non-tier-3) documents."""
    allowed_roles = _parse_role_set("API_PURGE_ANY_TIER_ROLES", "owner")
    if not allowed_roles:
        return
    role = (x_admin_role or "").strip().lower()
    if role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=(
                "Purge for non-project tiers requires elevated role. "
                f"Allowed roles: {sorted(allowed_roles)}."
            ),
        )


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


def _remove_local_raw_file(local_path: Optional[str]) -> bool:
    """Delete local raw file if it exists under documents/raw."""
    if not local_path:
        return False
    try:
        path = Path(local_path).resolve()
    except OSError:
        return False
    raw_root = Path("documents/raw").resolve()
    try:
        path.relative_to(raw_root)
    except ValueError:
        return False
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True


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


@router.post(
    "/{doc_id}/purge-project-upload",
    response_model=DocumentAdminActionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Not a project upload or invalid purge request"},
        403: {"model": ErrorResponse, "description": "Invalid admin token"},
        503: {"model": ErrorResponse, "description": "Admin auth misconfiguration"},
        404: {"model": ErrorResponse, "description": "Document not found"},
        500: {"model": ErrorResponse, "description": "Purge failure"},
    },
    summary="Purge project upload chunks/vectors and tombstone metadata",
)
def purge_project_upload_admin(
    doc_id: str,
    x_admin_token: Optional[str] = Header(default=None),
    x_admin_role: Optional[str] = Header(default=None),
    x_admin_user: Optional[str] = Header(default=None),
) -> DocumentAdminActionResponse:
    """Purge project-upload content while retaining governance document row."""
    _require_admin_auth(x_admin_token, x_admin_role)
    try:
        row = db_client.get_document_by_doc_id(doc_id)
    except Exception as exc:
        log.exception("Purge lookup failed for doc_id=%s", doc_id)
        raise HTTPException(status_code=500, detail=f"Purge lookup error: {exc}") from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    source_tier = int(row.get("source_tier", 1))
    if source_tier != 3:
        _require_any_tier_purge_role(x_admin_role)
    actor_role = (x_admin_role or "").strip().lower() or "unknown"
    actor_identity = (x_admin_user or "").strip() or "unknown"
    try:
        deleted_chunks = db_client.delete_chunks_for_document(row["id"])
        file_deleted = _remove_local_raw_file(row.get("local_path"))
        updated = db_client.update_document_admin_fields(
            doc_id,
            document_status="repealed",
            is_current=False,
            retrieval_weight=0.0,
        )
        db_client.insert_purge_audit_log(
            doc_id=doc_id,
            document_id=row["id"],
            actor_identity=actor_identity,
            actor_role=actor_role,
            source_tier=source_tier,
            deleted_chunk_count=deleted_chunks,
            local_file_deleted=file_deleted,
        )
    except Exception as exc:
        log.exception("Project upload purge failed for doc_id=%s", doc_id)
        raise HTTPException(status_code=500, detail=f"Purge error: {exc}") from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    detail = _to_document_detail(updated)
    return DocumentAdminActionResponse(
        action="purge_project_upload",
        message=(
            f"Purged project upload {doc_id}: deleted_chunks={deleted_chunks}, "
            f"local_file_deleted={file_deleted}. Document retained as repealed."
        ),
        document=detail,
    )
