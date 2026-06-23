"""
api/routes/documents.py — Document metadata endpoints
=====================================================
Provides list/detail/status routes for document governance metadata.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

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
    )


@router.get(
    "",
    response_model=list[DocumentSummaryResponse],
    responses={500: {"model": ErrorResponse, "description": "Document list failure"}},
    summary="List documents",
    description="List document metadata with optional municipality/status/authority/doc_type filters.",
)
def list_document_metadata(
    municipality: str | None = Query(default=None),
    status: DocumentStatusType | None = Query(default=None),
    authority: AuthorityLevelType | None = Query(default=None),
    doc_type: DocTypeType | None = Query(default=None),
) -> list[DocumentSummaryResponse]:
    """Return document metadata rows with optional filters."""
    try:
        rows = db_client.list_documents(
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
    municipality: str | None = Query(default=None),
    status: DocumentStatusType | None = Query(default=None),
    authority: AuthorityLevelType | None = Query(default=None),
    doc_type: DocTypeType | None = Query(default=None),
) -> DocumentStatusResponse:
    """Return grouped status counts for the selected document filter scope."""
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
def get_document_detail(doc_id: str) -> DocumentDetailResponse:
    """Return full metadata for a single document by doc_id."""
    try:
        row = db_client.get_document_by_doc_id(doc_id)
    except Exception as exc:
        log.exception("Document detail lookup failed: %s", doc_id)
        raise HTTPException(status_code=500, detail=f"Document detail error: {exc}") from exc
    if row is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {doc_id}")
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
