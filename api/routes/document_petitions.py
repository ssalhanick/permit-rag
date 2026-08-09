"""
api/routes/document_petitions.py — Jurisdiction ordinance/code petitions.
==========================================================================
Type 1 of the document-upload plan: any authenticated user can petition a
jurisdiction-wide ordinance or code into the shared corpus. Tiered trust —
a verified contributor's petition auto-approves straight into tier 1 (same
as today's admin upload); everyone else's lands in a tier-2 pending queue
for staff review via GET/PATCH/POST /admin/documents/pending|approve|reject.

The admin trio is modeled directly on api/routes/overlays.py's
list_pending_overlays/approve_overlay_admin/reject_overlay_admin — same
shape, different target table. Reuses api.routes.upload's chunk/embed
background pipeline rather than duplicating it, same as overlays.py and
api/routes/project_documents.py do.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

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
from api.routes.upload import (
    ALLOWED_EXTENSIONS,
    UPLOAD_DIR,
    VALID_AUTHORITY_LEVELS,
    VALID_DOC_TYPES,
    UploadResponse,
    _check_petition_dedup,
    _check_petition_rate_limit,
    _process_upload,
)
from api.schemas import DocumentSummaryResponse, RejectDocumentRequest, SetVerifiedContributorRequest
from db import client as db_client
from rag.jurisdiction_ids import canonicalize

log = logging.getLogger(__name__)
router = APIRouter(tags=["document-petitions"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


def _to_document_summary(row: dict) -> DocumentSummaryResponse:
    """Convert a DB document row to the shared summary schema (matches the
    equivalent private helper duplicated in api/routes/documents.py and
    api/routes/admin.py, rather than importing a cross-file private function)."""
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


@router.post(
    "/documents/petitions",
    response_model=UploadResponse,
    status_code=201,
    summary="Petition a jurisdiction ordinance/code into the shared corpus",
)
async def petition_document(
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="The ordinance/code source document (PDF or HTML)."),
    municipality: str = Form(..., description="Jurisdiction name, e.g. 'Dallas' or 'Plano'."),
    authority_level: str = Form(..., description="municipal | county | state | federal."),
    doc_type: str = Form(..., description="e.g. 'zoning_ordinance', 'building_code'."),
    subject_tags: str = Form(default="", description="Comma-separated subject tags."),
) -> UploadResponse:
    """
    Any authenticated user can petition an ordinance. A verified contributor
    (``users.is_verified_contributor``, staff-granted) skips the queue and
    goes straight to the shared corpus, same as an admin upload. Everyone
    else's petition lands as a pending tier-2 draft for staff review via the
    /admin/documents/pending|approve|reject trio below.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )
    if authority_level not in VALID_AUTHORITY_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid authority_level. Choose from: {sorted(VALID_AUTHORITY_LEVELS)}",
        )
    if doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type. Choose from: {sorted(VALID_DOC_TYPES)}",
        )
    canonical_municipality = canonicalize(municipality)
    if not canonical_municipality:
        raise HTTPException(status_code=400, detail="municipality is required.")

    user_row = db_client.get_user_by_id(current_user["user_id"])
    is_verified = bool(user_row and user_row.get("is_verified_contributor"))

    _check_petition_rate_limit(current_user["user_id"])

    content = await file.read()
    await file.close()
    checksum = hashlib.sha256(content).hexdigest()
    _check_petition_dedup(checksum)

    doc_id = f"ordinance-petition-{uuid4().hex}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{doc_id}{suffix}"
    try:
        dest.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc

    tags = [t.strip() for t in subject_tags.split(",") if t.strip()] if subject_tags else []

    background_tasks.add_task(
        _process_upload,
        doc_id=doc_id,
        local_path=str(dest),
        source_url=f"file://{dest.resolve()}",
        municipality=canonical_municipality,
        authority_level=authority_level,
        doc_type=doc_type,
        subject_tags=tags,
        source_tier=1 if is_verified else 2,
        uploaded_by=current_user["user_id"],
        auto_activate=is_verified,
    )

    log.info(
        "Ordinance petitioned: doc_id=%s municipality=%s verified=%s user_id=%s",
        doc_id, canonical_municipality, is_verified, current_user["user_id"],
    )
    message = (
        f"File '{file.filename}' accepted and will be auto-approved into the shared corpus "
        f"(verified contributor)."
        if is_verified
        else f"File '{file.filename}' accepted and queued for staff review."
    )
    return UploadResponse(doc_id=doc_id, status="processing", message=message, local_path=str(dest))


@router.get(
    "/admin/documents/pending",
    response_model=list[DocumentSummaryResponse],
    summary="List ordinance petitions awaiting staff review",
)
def list_pending_documents(
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> list[DocumentSummaryResponse]:
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    rows = db_client.get_pending_documents()
    return [_to_document_summary(row) for row in rows]


@router.patch(
    "/admin/documents/{doc_id}/approve",
    response_model=DocumentSummaryResponse,
    summary="Approve a pending ordinance petition into the shared corpus",
)
def approve_document_admin(
    doc_id: str,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> DocumentSummaryResponse:
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    row = db_client.approve_pending_document(doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pending document not found.")
    return _to_document_summary(row)


@router.post(
    "/admin/documents/{doc_id}/reject",
    summary="Reject a pending ordinance petition",
)
def reject_document_admin(
    doc_id: str,
    body: RejectDocumentRequest | None = None,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> dict:
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    reason = body.reason if body else None
    if not db_client.reject_pending_document(doc_id, reason=reason):
        raise HTTPException(status_code=404, detail="Pending document not found.")
    return {"detail": f"Rejected pending document {doc_id}."}


@router.patch(
    "/admin/users/{user_id}/verified-contributor",
    summary="Grant or revoke tiered-trust auto-approval for ordinance petitions",
)
def set_verified_contributor_admin(
    user_id: UUID,
    body: SetVerifiedContributorRequest,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> dict:
    """Staff-only. Deliberately returns a hand-picked field subset, not the
    raw users row (which carries password_hash/refresh_token_hash)."""
    _require_admin_auth(x_admin_token, x_admin_role, current_user)
    row = db_client.set_user_verified_contributor(user_id, body.is_verified_contributor)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found or inactive.")
    return {
        "id": row["id"],
        "username": row["username"],
        "is_verified_contributor": row["is_verified_contributor"],
    }
