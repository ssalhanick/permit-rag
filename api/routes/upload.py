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
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/documents", tags=["admin-upload"])

# ── Auth (reuses existing admin token logic) ─────────────────

_token_header = APIKeyHeader(name="X-Admin-Token", auto_error=False)


def _require_admin(token: str | None = Depends(_token_header)) -> None:
    """Raise 401/403 if the request lacks a valid admin token."""
    required = os.environ.get("API_ADMIN_AUTH_REQUIRED", "true").lower() not in {"0", "false", "no"}
    if not required:
        return
    expected = os.environ.get("API_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=500, detail="API_ADMIN_TOKEN is not configured.")
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")


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
) -> None:
    """
    Run in background: insert document row, chunk, and embed.
    Sets document_status = 'active' on success, 'needs_ocr' on failure.
    """
    from db.client import get_document_by_doc_id, insert_document, update_document_admin_fields
    from ingestion.chunker import chunk_document
    from ingestion.embedder import embed_document_chunks

    log.info("Background processing started for doc_id=%s", doc_id)
    try:
        checksum = hashlib.sha256(Path(local_path).read_bytes()).hexdigest()
        doc_row = insert_document(
            doc_id=doc_id,
            source_url=source_url,
            municipality=municipality,
            authority_level=authority_level,
            doc_type=doc_type,
            subject_tags=subject_tags,
            document_status="active",
            checksum_sha256=checksum,
            local_path=local_path,
            source_tier=source_tier,
        )
        document_uuid = doc_row["id"]
        chunks = chunk_document(local_path, doc_id=doc_id)
        embed_document_chunks(document_uuid, chunks)
        log.info(
            "Upload processing complete: doc_id=%s chunks=%d", doc_id, len(chunks)
        )
    except Exception as exc:
        log.exception("Upload processing failed for doc_id=%s: %s", doc_id, exc)
        try:
            update_document_admin_fields(doc_id, document_status="needs_ocr")
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
    _auth: None = Depends(_require_admin),
    file: UploadFile = File(..., description="PDF or HTML file to upload."),
    doc_id: str = Form(..., description="Unique document identifier (e.g. 'plano-pool-ordinance-2024')."),
    municipality: str = Form(..., description="Municipality string matching documents table (e.g. 'plano')."),
    authority_level: str = Form(..., description="Authority level: municipal | state | federal | regional."),
    doc_type: str = Form(..., description="Document type (e.g. 'zoning_ordinance')."),
    subject_tags: str = Form(default="", description="Comma-separated subject tags (e.g. 'pools,setbacks')."),
    source_tier: int = Form(default=2, description="Source tier: 1=corpus, 2=user ordinance, 3=project doc."),
    source_url: Optional[str] = Form(default=None, description="Source URL if document was obtained online."),
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
    )

    return UploadResponse(
        doc_id=doc_id,
        status="processing",
        message=(
            f"File '{file.filename}' accepted. Chunking and embedding running in background. "
            f"Poll GET /documents/{doc_id} to check status."
        ),
        local_path=local_path,
    )
