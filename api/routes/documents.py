"""
api/routes/documents.py — Document metadata endpoints
=====================================================
Provides list/detail/status routes for document governance metadata.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from api.auth import get_current_user, is_staff, is_superadmin
from api.schemas import (
    AuthorityLevelType,
    DocTypeType,
    DocumentDetailResponse,
    DocumentStatusCountResponse,
    DocumentStatusResponse,
    DocumentStatusType,
    DocumentSummaryResponse,
    ErrorResponse,
)
from db import client as db_client

log = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _to_document_summary(row: dict) -> DocumentSummaryResponse:
    """Convert a DB document row to summary response model."""
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
        uploaded_by=row.get("uploaded_by"),
        project_id=row.get("project_id"),
        source_tier=row.get("source_tier"),
    )


def _can_view_document(row: dict, current_user: dict) -> bool:
    """True if current_user may see this document's metadata/content.

    Staff see everything. Everyone else: tiers 1/2 (shared corpus, pending
    ordinance petitions) are visible to any authenticated user same as
    before this fix — the exposure this closes is tier-3 (project) documents,
    which are scoped to the uploader or, for 'team' visibility, the project's
    members (mirrors match_project_chunks' and match_chunks' migration-045
    retrieval filter).
    """
    if is_staff(current_user):
        return True
    if row.get("source_tier") != 3:
        return True
    if row.get("uploaded_by") == current_user["user_id"]:
        return True
    if row.get("visibility") == "team" and row.get("project_id"):
        return bool(db_client.get_project_role(row["project_id"], current_user["user_id"]))
    return False


@router.get(
    "",
    response_model=list[DocumentSummaryResponse],
    responses={500: {"model": ErrorResponse, "description": "Document list failure"}},
    summary="List documents",
    description="List document metadata with optional municipality/status/authority/doc_type filters.",
)
def list_document_metadata(
    current_user: CurrentUser,
    municipality: str | None = Query(default=None),
    status: DocumentStatusType | None = Query(default=None),
    authority: AuthorityLevelType | None = Query(default=None),
    doc_type: DocTypeType | None = Query(default=None),
    scope: str | None = Query(
        default=None,
        description="'mine' forces the personal Document Library view even for superadmins.",
    ),
) -> list[DocumentSummaryResponse]:
    """
    Return document metadata rows with optional filters.

    Superadmins get the full corpus by default — this endpoint doubles as
    the corpus browser's data source, and "only super users can see the
    document corpus" is the explicit product decision (bulk browsing is the
    sensitive operation, distinct from a single citation lookup — see
    get_document_detail). Everyone else gets their own scoped "Document
    Library" (owned or team-shared tier-3 docs only; see
    db_client.list_documents_for_user) — previously this endpoint had no
    auth at all and returned the full corpus to any caller, authenticated or
    not.

    ``scope=mine`` forces the personal-library query regardless of role, so
    a superadmin's own Document Library page shows their own documents
    instead of the entire corpus (the corpus browser is a separate page).
    """
    try:
        if is_superadmin(current_user) and scope != "mine":
            rows = db_client.list_documents(
                municipality=municipality,
                status=status,
                authority_level=authority,
                doc_type=doc_type,
            )
        else:
            rows = db_client.list_documents_for_user(
                current_user["user_id"],
                municipality=municipality,
                status=status,
                authority_level=authority,
                doc_type=doc_type,
            )
    except Exception as exc:
        log.exception("Document listing failed")
        raise HTTPException(status_code=500, detail=f"Document list error: {exc}") from exc
    return [_to_document_summary(row) for row in rows]


@router.get(
    "/status",
    response_model=DocumentStatusResponse,
    responses={500: {"model": ErrorResponse, "description": "Document status failure"}},
    summary="Get document status counts",
    description="Return document_status counts for optional municipality/status/authority/doc_type filters.",
)
def document_status_counts(
    current_user: CurrentUser,
    municipality: str | None = Query(default=None),
    status: DocumentStatusType | None = Query(default=None),
    authority: AuthorityLevelType | None = Query(default=None),
    doc_type: DocTypeType | None = Query(default=None),
) -> DocumentStatusResponse:
    """
    Return grouped status counts for the selected document filter scope.

    Aggregate counts only (no document content/identity) — kept corpus-wide
    for any authenticated user rather than scoped like the listing/detail
    routes, but now requires login instead of being fully anonymous.
    """
    del current_user  # auth-gate only; counts are corpus-wide, not per-user
    try:
        rows = db_client.get_document_status_counts(
            municipality=municipality,
            status=status,
            authority_level=authority,
            doc_type=doc_type,
        )
    except Exception as exc:
        log.exception("Document status aggregation failed")
        raise HTTPException(status_code=500, detail=f"Document status error: {exc}") from exc
    counts = [
        DocumentStatusCountResponse(status=row["document_status"], count=row["count"])
        for row in rows
    ]
    total_documents = sum(bucket.count for bucket in counts)
    return DocumentStatusResponse(
        municipality=municipality,
        authority=authority,
        doc_type=doc_type,
        status=status,
        total_documents=total_documents,
        counts=counts,
    )


@router.get(
    "/{doc_id}",
    response_model=DocumentDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Document not found"},
        500: {"model": ErrorResponse, "description": "Document detail failure"},
    },
    summary="Get document details by doc_id",
    description="Fetch full document metadata and stored chunk count for one doc_id.",
)
def get_document_detail(doc_id: str, current_user: CurrentUser) -> DocumentDetailResponse:
    """Return full metadata for a single document by doc_id."""
    try:
        row = db_client.get_document_by_doc_id(doc_id)
    except Exception as exc:
        log.exception("Document detail lookup failed: %s", doc_id)
        raise HTTPException(status_code=500, detail=f"Document detail error: {exc}") from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    if not _can_view_document(row, current_user):
        raise HTTPException(status_code=403, detail="Insufficient privileges for this document.")
    try:
        chunk_count = db_client.count_chunks(row["id"])
    except Exception as exc:
        log.exception("Chunk counting failed for doc_id=%s", doc_id)
        raise HTTPException(status_code=500, detail=f"Chunk count error: {exc}") from exc
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


@router.get(
    "/{doc_id}/download",
    responses={
        403: {"model": ErrorResponse, "description": "Insufficient privileges"},
        404: {"model": ErrorResponse, "description": "Document not found or no stored file"},
    },
    summary="Download a document's original stored file",
)
def download_document(doc_id: str, current_user: CurrentUser) -> FileResponse:
    """Stream the document's stored file, same access rule as get_document_detail.

    Only documents with a local_path (uploaded files) can be downloaded —
    tier-1 corpus rows sourced from a scraped URL have no local copy to serve.
    """
    row = db_client.get_document_by_doc_id(doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
    if not _can_view_document(row, current_user):
        raise HTTPException(status_code=403, detail="Insufficient privileges for this document.")
    local_path = row.get("local_path")
    if not local_path or not Path(local_path).is_file():
        raise HTTPException(status_code=404, detail="No stored file for this document.")
    filename = Path(local_path).name
    return FileResponse(local_path, filename=filename)
