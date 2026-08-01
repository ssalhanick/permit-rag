"""
api/routes/project_documents.py — Project-specific (tier-3) document uploads.
==============================================================================
Type 2 of the document-upload plan: a project member attaches private
reference material (drawings, plans, spreadsheets, CAD) to their own project.
No approval workflow — instant, unlike Type 1's tiered-trust ordinance
petitions or Type 3's overlay petitions.

Namespaced under /documents/upload (not the bare /projects/{id}/documents
POST/DELETE pair) because that path is already live: api/routes/projects.py's
share_document/unshare_document link an *existing* document into a project by
reference (JSON body, no file) and the frontend already calls it
(shareDocumentToProject in frontend/src/api.js). This is a different
operation — upload a *new* file, hard-delete it with its chunks — and reusing
that path would either collide or silently change the existing endpoint's
contract.

Reuses api.routes.upload's chunk/embed background pipeline exactly like
api/routes/overlays.py does, rather than duplicating it.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from api.auth import get_current_user
from api.routes.projects import _require_role
from api.routes.upload import UPLOAD_DIR, UploadResponse, _process_upload
from api.schemas import DocumentVisibilityType
from db import client as db_client

log = logging.getLogger(__name__)
router = APIRouter(tags=["project-documents"])
CurrentUser = Annotated[dict, Depends(get_current_user)]

# Real text/vision content the existing pipeline (ingestion/chunker.py) can
# already parse — chunked and embedded like any other document.
CHUNKABLE_EXTENSIONS = {".pdf", ".html", ".htm", ".docx", ".pptx", ".txt", ".md", ".markdown"}

# Accepted at upload but stored as an artifact only — no chunk/embed step.
# Images are here (not chunked) because no OCR pipeline exists anywhere in
# this repo (no pytesseract/OCR dependency, no extraction path in
# ingestion/chunker.py) — "images-via-OCR" is an MVP-plan aspiration, not a
# built feature, so building one here would be exactly the kind of bigger,
# separate parser project the plan already scopes CAD out for. Spreadsheets
# and CAD were never claimed as chunkable by the plan.
ARTIFACT_ONLY_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".tiff", ".tif", ".bmp", ".webp",
    ".xlsx", ".xls", ".csv",
    ".dwg", ".dxf",
}

PROJECT_DOC_ALLOWED_EXTENSIONS = CHUNKABLE_EXTENSIONS | ARTIFACT_ONLY_EXTENSIONS

# documents.authority_level has no "private project reference" tier — same
# imperfect-fit call api/routes/overlays.py already made for HOA bylaws.
_PROJECT_DOC_AUTHORITY_LEVEL = "municipal"
_PROJECT_DOC_TYPE = "other"


@router.post(
    "/projects/{project_id}/documents/upload",
    response_model=UploadResponse,
    status_code=201,
    summary="Upload a private or team-visible document to this project",
)
async def upload_project_document(
    project_id: UUID,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Drawing, plan, spreadsheet, image, or CAD file."),
    visibility: DocumentVisibilityType = Form(
        default="team", description="private (uploader only) or team (whole project)."
    ),
    subject_tags: str = Form(default="", description="Comma-separated subject tags."),
) -> UploadResponse:
    """
    Any project editor/owner can attach reference material to their project.

    Chunkable formats (PDF/DOCX/PPTX/HTML/TXT/MD) are chunked and embedded in
    the background, same as the admin upload path. Spreadsheets, images, and
    CAD files are stored but not chunked — inserted directly with a terminal
    'active' status since there is no processing step to wait on.
    """
    _require_role(project_id, current_user["user_id"], {"owner", "editor"}, current_user)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in PROJECT_DOC_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(PROJECT_DOC_ALLOWED_EXTENSIONS)}",
        )

    project = db_client.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    doc_id = f"project-doc-{uuid4().hex}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"{doc_id}{suffix}"
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc
    finally:
        await file.close()

    tags = [t.strip() for t in subject_tags.split(",") if t.strip()] if subject_tags else []
    municipality = project.get("municipality") or "unknown"
    source_url = f"file://{dest.resolve()}"

    if suffix in ARTIFACT_ONLY_EXTENSIONS:
        checksum = hashlib.sha256(dest.read_bytes()).hexdigest()
        doc_row = db_client.insert_document(
            doc_id=doc_id,
            source_url=source_url,
            municipality=municipality,
            authority_level=_PROJECT_DOC_AUTHORITY_LEVEL,
            doc_type=_PROJECT_DOC_TYPE,
            subject_tags=tags,
            document_status="active",
            checksum_sha256=checksum,
            local_path=str(dest),
            source_tier=3,
            project_id=project_id,
            uploaded_by=current_user["user_id"],
            visibility=visibility,
        )
        db_client.share_document_to_project(project_id, doc_row["id"], current_user["user_id"])
        log.info(
            "Project document stored as artifact-only (no chunking): doc_id=%s project_id=%s suffix=%s",
            doc_id, project_id, suffix,
        )
        return UploadResponse(
            doc_id=doc_id,
            status="active",
            message=f"File '{file.filename}' stored. This file type isn't chunked for search — download it from the project's document list.",
            local_path=str(dest),
        )

    background_tasks.add_task(
        _process_upload,
        doc_id=doc_id,
        local_path=str(dest),
        source_url=source_url,
        municipality=municipality,
        authority_level=_PROJECT_DOC_AUTHORITY_LEVEL,
        doc_type=_PROJECT_DOC_TYPE,
        subject_tags=tags,
        source_tier=3,
        project_id=project_id,
        uploaded_by=current_user["user_id"],
        visibility=visibility,
    )
    log.info("Project document upload accepted: doc_id=%s project_id=%s", doc_id, project_id)
    return UploadResponse(
        doc_id=doc_id,
        status="processing",
        message=(
            f"File '{file.filename}' accepted. Chunking and embedding running in background. "
            f"Poll GET /documents/{doc_id} until document_status is active or needs_ocr."
        ),
        local_path=str(dest),
    )


@router.delete(
    "/projects/{project_id}/documents/upload/{document_id}",
    summary="Permanently delete a project document and its chunks",
)
def delete_project_document(
    project_id: UUID,
    document_id: UUID,
    current_user: CurrentUser,
) -> dict:
    """
    Hard-delete — removes the document row and all of its chunks in one
    transaction (db_client.delete_project_document), unlike
    DELETE /projects/{project_id}/documents/{document_id} (unshare_document),
    which only unlinks a shared-by-reference document and leaves it intact.

    Gated the same as upload (owner/editor) rather than uploader-only: only
    editors/owners can upload in the first place, so this doesn't newly
    expose delete to anyone who couldn't already remove the file's usefulness
    by other means (e.g. re-uploading over it).
    """
    _require_role(project_id, current_user["user_id"], {"owner", "editor"}, current_user)

    doc = db_client.get_document_by_uuid(document_id)
    if not doc or doc.get("source_tier") != 3 or str(doc.get("project_id")) != str(project_id):
        raise HTTPException(status_code=404, detail="Project document not found.")

    if not db_client.delete_project_document(document_id):
        raise HTTPException(status_code=404, detail="Project document not found.")
    log.info(
        "Project document deleted: document_id=%s project_id=%s by user_id=%s",
        document_id, project_id, current_user["user_id"],
    )
    return {"detail": "Document permanently deleted."}
