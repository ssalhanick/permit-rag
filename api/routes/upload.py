"""
api/routes/upload.py — Admin document upload endpoint
======================================================
POST /admin/documents/upload

Accepts a PDF or HTML file plus required metadata, saves it to
documents/raw/, and triggers chunk + embed as a FastAPI background task.
Guarded by the existing admin token (X-Admin-Token header).

Response is immediate — upload completes, processing continues in background.
Poll GET /documents/{doc_id} to check when document_status transitions from
'processing' → 'active'.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from pathlib import Path
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from api.auth import get_optional_current_user
from db.client import (
    delete_chunks_for_document,
    insert_chunks,
    insert_document,
    share_document_to_project,
    update_document_admin_fields,
)
from ingestion.chunker import chunk_document
from ingestion.embedder import embed_document

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/documents", tags=["admin-upload"])


def _is_html_path(local_path: str) -> bool:
    """Return true when local_path is an HTML file."""
    suffix = Path(local_path).suffix.lower()
    return suffix in {".html", ".htm"}


def _retry_chunk_html_without_filter(doc_id: str, local_path: str) -> dict:
    """Retry chunking once for HTML with procedural filter disabled."""
    if not _is_html_path(local_path):
        return chunk_document(doc_id)
    prior = os.environ.get("CHUNK_PROCEDURAL_FILTER_ENABLED")
    try:
        os.environ["CHUNK_PROCEDURAL_FILTER_ENABLED"] = "false"
        return chunk_document(doc_id)
    finally:
        if prior is None:
            os.environ.pop("CHUNK_PROCEDURAL_FILTER_ENABLED", None)
        else:
            os.environ["CHUNK_PROCEDURAL_FILTER_ENABLED"] = prior


def _failure_status(local_path: str) -> str:
    """Map processing failures to document lifecycle status by file type."""
    return "needs_ocr" if Path(local_path).suffix.lower() == ".pdf" else "draft"

# ── Auth (reuses existing admin token logic) ─────────────────

_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def _require_admin_or_jwt(
    token: str | None = Depends(_token_header),
    current_user: dict | None = Depends(get_optional_current_user),
) -> dict | None:
    """Require either a valid X-Admin-Token or a valid logged-in JWT user."""
    required = os.environ.get("API_ADMIN_AUTH_REQUIRED", "true").lower() not in {"0", "false", "no"}
    if not required:
        return current_user or {"user_id": None, "role": "admin", "username": "system-admin"}

    # Check legacy X-Admin-Token
    expected = os.environ.get("API_ADMIN_TOKEN", "").strip()
    if expected and token == expected:
        return {"user_id": None, "role": "admin", "username": "system-admin"}

    # Check JWT user
    if current_user:
        return current_user

    raise HTTPException(status_code=401, detail="Authentication required. Provide a valid admin token or log in.")


# ── Background processing task ───────────────────────────────

def _process_upload(
    *,
    doc_id: str,
    local_path: str,
    source_url: str,
    municipality: str,
    authority_level: str,
    doc_type: str,
    subject_tags: list[str],
    source_tier: int,
    project_id: UUID | None = None,
    uploaded_by: UUID | None = None,
) -> None:
    """
    Run in background: insert document row, chunk, and embed.
    Sets document_status = 'active' on success, 'needs_ocr' on failure.
    """
    log.info("Background processing started for doc_id=%s project_id=%s uploaded_by=%s", doc_id, project_id, uploaded_by)
    try:
        checksum = hashlib.sha256(Path(local_path).read_bytes()).hexdigest()
        doc_row = insert_document(
            doc_id=doc_id,
            source_url=source_url,
            municipality=municipality,
            authority_level=authority_level,
            doc_type=doc_type,
            subject_tags=subject_tags,
            document_status="draft",
            checksum_sha256=checksum,
            local_path=local_path,
            source_tier=source_tier,
            project_id=project_id,
            uploaded_by=uploaded_by,
        )
        document_uuid = doc_row["id"]
        if project_id:
            share_document_to_project(project_id, document_uuid, uploaded_by)

        chunk_result = chunk_document(doc_id)
        chunks = chunk_result["chunks"]
        if not chunks and _is_html_path(local_path):
            log.warning("No chunks from HTML on first pass; retrying without procedural filter: %s", doc_id)
            chunk_result = _retry_chunk_html_without_filter(doc_id, local_path)
            chunks = chunk_result["chunks"]
        if not chunks:
            raise RuntimeError(f"No chunks produced for doc_id={doc_id}")
        delete_chunks_for_document(document_uuid)
        inserted = insert_chunks(document_uuid, chunks)
        embed_result = embed_document(doc_id, force=True)
        update_document_admin_fields(doc_id, document_status="active")
        log.info(
            "Upload processing complete: doc_id=%s chunks=%d embedded_new=%s",
            doc_id,
            inserted,
            embed_result.get("num_new"),
        )
    except Exception as exc:
        log.exception("Upload processing failed for doc_id=%s: %s", doc_id, exc)
        try:
            update_document_admin_fields(doc_id, document_status=_failure_status(local_path))
        except Exception:
            pass


# ── Response model ────────────────────────────────────────────

class UploadResponse(BaseModel):
    doc_id: str
    status: str
    message: str
    local_path: str


# ── Endpoint ─────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".pdf", ".html", ".htm"}
UPLOAD_DIR = Path("documents/raw")

# Valid enum values (must match Postgres enums in schema)
VALID_AUTHORITY_LEVELS = {"municipal", "state", "federal", "regional"}
VALID_DOC_TYPES = {
    "building_code", "zoning_ordinance", "fire_code", "electrical_code",
    "plumbing_code", "mechanical_code", "energy_code", "accessibility_standard",
    "environmental_regulation", "licensing_requirement", "permit_guide", "other",
}


@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a permit document for ingestion",
    description=(
        "Upload a PDF or HTML permit document. The file is saved to documents/raw/ "
        "and chunked + embedded in the background. Requires X-Admin-Token header. "
        "Poll GET /documents/{doc_id} to check processing status."
    ),
)
async def upload_document(
    background_tasks: BackgroundTasks,
    auth_user: dict | None = Depends(_require_admin_or_jwt),
    file: UploadFile = File(..., description="PDF or HTML file to upload."),
    doc_id: str = Form(..., description="Unique document identifier (e.g. 'plano-pool-ordinance-2024')."),
    municipality: str = Form(..., description="Municipality string matching documents table (e.g. 'plano')."),
    authority_level: str = Form(..., description="Authority level: municipal | state | federal | regional."),
    doc_type: str = Form(..., description="Document type (e.g. 'zoning_ordinance')."),
    subject_tags: str = Form(default="", description="Comma-separated subject tags (e.g. 'pools,setbacks')."),
    source_tier: int = Form(default=2, description="Source tier: 1=corpus, 2=user ordinance, 3=project doc."),
    source_url: str | None = Form(default=None, description="Source URL if document was obtained online."),
    project_id: UUID | None = Form(default=None, description="Optional project UUID to bind/share document to."),
) -> UploadResponse:
    # ── Validate inputs ──────────────────────────────────────
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )
    if not doc_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail="doc_id may only contain alphanumeric characters, hyphens, and underscores.",
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
    if source_tier not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="source_tier must be 1, 2, or 3.")
    if project_id and not db_client.get_project(project_id):
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_id} not found.",
        )

    # Resolve uploaded_by user_id
    uploaded_by = auth_user.get("user_id") if (auth_user and isinstance(auth_user, dict)) else None

    # ── Save file ────────────────────────────────────────────
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
    local_path = str(dest)
    effective_source_url = source_url or f"file://{dest.resolve()}"

    log.info(
        "File saved: doc_id=%s path=%s size=%d bytes",
        doc_id, local_path, dest.stat().st_size,
    )

    # ── Kick off background processing ──────────────────────
    background_tasks.add_task(
        _process_upload,
        doc_id=doc_id,
        local_path=local_path,
        source_url=effective_source_url,
        municipality=municipality,
        authority_level=authority_level,
        doc_type=doc_type,
        subject_tags=tags,
        source_tier=source_tier,
        project_id=project_id,
        uploaded_by=uploaded_by,
    )

    return UploadResponse(
        doc_id=doc_id,
        status="processing",
        message=(
            f"File '{file.filename}' accepted. Chunking and embedding running in background. "
            f"Poll GET /documents/{doc_id} until document_status is active or needs_ocr."
        ),
        local_path=local_path,
    )
