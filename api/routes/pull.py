"""
api/routes/pull.py — On-demand URL pull (docs/on_demand_url_pull.md)
=====================================================================
POST /admin/documents/pull-page      → { job_id, status: "processing" }
GET  /admin/documents/pull-jobs/{id} → progress + per-file results

Fetches an admin-supplied page, discovers linked files, and ingests
only what changed. Identity: normalized URL first, then
municipality + doc_type + filename fallback (sets url_changed flag).
Old versions are superseded ONLY after the new version chunks + embeds.

Auth: same dual-path admin gate as admin.py -- a verified Cognito session
with role='admin', OR the shared X-Admin-Token (kept only as a machine
credential for scripts, never collected in the frontend UI).
Job state is an in-memory dict (MVP) — a DB-backed table is a later upgrade.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_optional_current_user
from api.routes.admin import _require_admin_auth
from api.routes.upload import (
    VALID_AUTHORITY_LEVELS,
    VALID_DOC_TYPES,
    _failure_status,
    _is_html_path,
    _retry_chunk_html_without_filter,
)
from db.client import (
    delete_chunks_for_document,
    find_document_by_checksum,
    find_document_by_fallback_identity,
    find_document_by_source_url_norm,
    get_document_by_doc_id,
    insert_chunks,
    insert_document,
    set_document_source_identity,
    update_document_admin_fields,
)
from ingestion.chunker import chunk_document
from ingestion.embedder import embed_document
from ingestion.governance import run_supersession_flow, sha256_bytes
from ingestion.page_crawler import (
    AssetLink,
    discover_asset_links,
    fetch_asset,
    validate_pull_url,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/documents", tags=["admin-pull"])

RAW_DIR = Path("documents/raw")

# Loose MIME sanity check per extension (empty content-type is tolerated).
_MIME_HINTS: dict[str, tuple[str, ...]] = {
    ".pdf": ("application/pdf",),
    ".html": ("text/html",),
    ".htm": ("text/html",),
    ".docx": ("application/vnd.openxmlformats", "application/octet-stream"),
    ".pptx": ("application/vnd.openxmlformats", "application/octet-stream"),
    ".txt": ("text/plain", "application/octet-stream"),
    ".md": ("text/plain", "text/markdown", "application/octet-stream"),
}

# ── In-memory job store (MVP) ────────────────────────────────

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


# ── Schemas ──────────────────────────────────────────────────

class PullPageRequest(BaseModel):
    url: str = Field(..., description="HTTPS page URL to pull linked files from.")
    municipality: str = Field(..., description="Municipality (e.g. 'dallas').")
    authority_level: str = Field(..., description="municipal | county | state | federal.")
    doc_type: str = Field(..., description="Document type enum value.")
    subject_tags: list[str] = Field(default_factory=list)
    source_tier: int = Field(default=2, description="1=corpus, 2=user ordinance, 3=project doc.")


class PullFileResult(BaseModel):
    url: str
    filename: str
    verdict: str  # new | updated | skipped | flagged | failed
    doc_id: str | None = None
    url_changed: bool = False
    detail: str | None = None


class PullJobResponse(BaseModel):
    job_id: str
    status: str  # processing | complete | failed
    page_url: str
    total_files: int = 0
    processed_files: int = 0
    files: list[PullFileResult] = Field(default_factory=list)
    error: str | None = None


class PullAcceptedResponse(BaseModel):
    job_id: str
    status: str
    message: str


# ── Ingest helper (upload's proven order) ────────────────────

def _sanitize_doc_id(raw: str) -> str:
    """Reduce arbitrary text to a safe doc_id fragment."""
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", raw.lower()).strip("-")
    return re.sub(r"-{2,}", "-", cleaned) or "doc"


def _new_doc_id(base: str) -> str:
    """Return *base*, date-tagged and uniquified until unused in the DB."""
    candidate = base
    if get_document_by_doc_id(candidate) is None:
        return candidate
    date_tag = datetime.now(UTC).strftime("%Y%m%d")
    candidate = f"{base}-{date_tag}"
    while get_document_by_doc_id(candidate) is not None:
        candidate = f"{base}-{date_tag}-{uuid4().hex[:6]}"
    return candidate


def _ingest_asset(
    doc_id: str,
    content: bytes,
    checksum: str,
    link: AssetLink,
    req: PullPageRequest,
) -> None:
    """
    Save raw bytes then insert → chunk → insert chunks → embed → activate.
    Raises on any failure; marks the new row needs_ocr/draft before raising
    so the previously active document is never superseded on failure.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    local_path = str(RAW_DIR / f"{doc_id}{link.extension}")
    Path(local_path).write_bytes(content)

    doc_row = insert_document(
        doc_id=doc_id,
        source_url=link.url,
        municipality=req.municipality,
        authority_level=req.authority_level,
        doc_type=req.doc_type,
        subject_tags=req.subject_tags,
        document_status="draft",
        checksum_sha256=checksum,
        local_path=local_path,
        source_tier=req.source_tier,
    )
    try:
        chunk_result = chunk_document(doc_id)
        chunks = chunk_result["chunks"]
        if not chunks and _is_html_path(local_path):
            chunk_result = _retry_chunk_html_without_filter(doc_id, local_path)
            chunks = chunk_result["chunks"]
        if not chunks:
            raise RuntimeError(f"No chunks produced for doc_id={doc_id}")
        delete_chunks_for_document(doc_row["id"])
        insert_chunks(doc_row["id"], chunks)
        embed_document(doc_id, force=True)
        update_document_admin_fields(doc_id, document_status="active")
    except Exception:
        update_document_admin_fields(doc_id, document_status=_failure_status(local_path))
        raise


# ── Per-file decision logic ──────────────────────────────────

def _resolve_identity(link: AssetLink, req: PullPageRequest) -> tuple[dict | None, bool]:
    """Return (existing_doc_row, matched_by_fallback)."""
    existing = find_document_by_source_url_norm(link.url_normalized)
    if existing is not None:
        return existing, False
    fallback = find_document_by_fallback_identity(
        req.municipality, req.doc_type, link.filename
    )
    return fallback, fallback is not None


def _mime_ok(extension: str, content_type: str) -> bool:
    """Loose sanity check of the served MIME type against the extension."""
    if not content_type:
        return True
    hints = _MIME_HINTS.get(extension, ())
    lowered = content_type.lower()
    return any(lowered.startswith(h) for h in hints)


def _process_asset(link: AssetLink, req: PullPageRequest) -> PullFileResult:
    """Fetch one discovered file and apply the identity/checksum decision table."""
    result = PullFileResult(url=link.url, filename=link.filename, verdict="failed")
    try:
        content, content_type = fetch_asset(link.url_normalized)
        if not _mime_ok(link.extension, content_type):
            result.detail = f"MIME mismatch: {content_type!r} for {link.extension}"
            return result

        checksum = sha256_bytes(content)
        existing, by_fallback = _resolve_identity(link, req)

        if existing is None:
            duplicate = find_document_by_checksum(checksum)
            if duplicate is not None:
                return _flag_duplicate(result, duplicate, link)
            return _ingest_brand_new(result, link, req, content, checksum)

        result.doc_id = existing["doc_id"]
        if existing.get("checksum_sha256") == checksum:
            return _handle_unchanged(result, existing, link, by_fallback)
        return _ingest_new_version(result, existing, link, req, content, checksum, by_fallback)
    except Exception as exc:
        log.exception("Pull failed for %s", link.url)
        result.verdict = "failed"
        result.detail = str(exc)
        return result


def _flag_duplicate(
    result: PullFileResult, duplicate: dict, link: AssetLink
) -> PullFileResult:
    """Same bytes already exist under another identity — human review, no supersede."""
    set_document_source_identity(
        duplicate["doc_id"], url_changed_flag=True, touch_last_pulled=True
    )
    result.verdict = "flagged"
    result.doc_id = duplicate["doc_id"]
    result.url_changed = True
    result.detail = (
        f"Content already ingested as {duplicate['doc_id']} at a different URL — "
        "flagged for review, not superseded."
    )
    return result


def _handle_unchanged(
    result: PullFileResult, existing: dict, link: AssetLink, by_fallback: bool
) -> PullFileResult:
    """Checksum matches the current document — skip (flag if URL moved)."""
    set_document_source_identity(
        existing["doc_id"],
        source_filename=link.filename,
        url_changed_flag=True if by_fallback else None,
        touch_last_pulled=True,
    )
    if by_fallback:
        result.verdict = "flagged"
        result.url_changed = True
        result.detail = "Same content found at a new URL — flagged for review."
    else:
        result.verdict = "skipped"
        result.detail = "Unchanged content — skipped."
    return result


def _ingest_brand_new(
    result: PullFileResult,
    link: AssetLink,
    req: PullPageRequest,
    content: bytes,
    checksum: str,
) -> PullFileResult:
    """No identity match anywhere — ingest as a new document."""
    stem = _sanitize_doc_id(Path(link.filename).stem)
    doc_id = _new_doc_id(f"{_sanitize_doc_id(req.municipality)}-{stem}")
    _ingest_asset(doc_id, content, checksum, link, req)
    set_document_source_identity(
        doc_id,
        source_url_normalized=link.url_normalized,
        source_filename=link.filename,
        touch_last_pulled=True,
    )
    result.verdict = "new"
    result.doc_id = doc_id
    return result


def _ingest_new_version(
    result: PullFileResult,
    existing: dict,
    link: AssetLink,
    req: PullPageRequest,
    content: bytes,
    checksum: str,
    by_fallback: bool,
) -> PullFileResult:
    """Content changed — ingest new version, then (only on success) supersede."""
    new_doc_id = _new_doc_id(existing["doc_id"])
    _ingest_asset(new_doc_id, content, checksum, link, req)
    set_document_source_identity(
        new_doc_id,
        source_url_normalized=link.url_normalized,
        source_filename=link.filename,
        url_changed_flag=by_fallback,
        touch_last_pulled=True,
    )
    run_supersession_flow(existing["doc_id"], new_doc_id)
    result.verdict = "updated"
    result.doc_id = new_doc_id
    result.url_changed = by_fallback
    if by_fallback:
        result.detail = "Matched by filename fallback — URL change flagged for review."
    return result


# ── Background job runner ────────────────────────────────────

def _run_pull_job(job_id: str, req: PullPageRequest) -> None:
    """Discover links on the page and process each file sequentially."""
    try:
        links = discover_asset_links(req.url)
        with _JOBS_LOCK:
            _JOBS[job_id]["total_files"] = len(links)
        for link in links:
            file_result = _process_asset(link, req)
            with _JOBS_LOCK:
                _JOBS[job_id]["files"].append(file_result)
                _JOBS[job_id]["processed_files"] += 1
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "complete"
    except Exception as exc:
        log.exception("Pull job %s failed", job_id)
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "failed"
            _JOBS[job_id]["error"] = str(exc)


# ── Endpoints ────────────────────────────────────────────────

@router.post(
    "/pull-page",
    response_model=PullAcceptedResponse,
    summary="Pull linked documents from a page URL",
)
def pull_page(
    body: PullPageRequest,
    background_tasks: BackgroundTasks,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> PullAcceptedResponse:
    """Validate the request, register a job, and process files in background.

    Superadmin-gated: this makes the server fetch and parse an admin-supplied
    URL (SSRF-adjacent), so it's held to a tighter bar than other admin routes.
    """
    _require_admin_auth(x_admin_token, x_admin_role, current_user, min_role="superadmin")

    if body.authority_level not in VALID_AUTHORITY_LEVELS:
        raise HTTPException(400, f"Invalid authority_level. Choose from: {sorted(VALID_AUTHORITY_LEVELS)}")
    if body.doc_type not in VALID_DOC_TYPES:
        raise HTTPException(400, f"Invalid doc_type. Choose from: {sorted(VALID_DOC_TYPES)}")
    if body.source_tier not in (1, 2, 3):
        raise HTTPException(400, "source_tier must be 1, 2, or 3.")
    try:
        validate_pull_url(body.url)
    except ValueError as exc:
        raise HTTPException(400, f"Unsafe or invalid URL: {exc}") from exc

    job_id = uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "processing",
            "page_url": body.url,
            "total_files": 0,
            "processed_files": 0,
            "files": [],
            "error": None,
        }
    background_tasks.add_task(_run_pull_job, job_id, body)
    return PullAcceptedResponse(
        job_id=job_id,
        status="processing",
        message=f"Pull started for {body.url}. Poll GET /admin/documents/pull-jobs/{job_id}.",
    )


@router.get(
    "/pull-jobs/{job_id}",
    response_model=PullJobResponse,
    summary="Poll a pull job for progress and per-file results",
)
def get_pull_job(
    job_id: str,
    x_admin_token: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> PullJobResponse:
    """Return current status and per-file verdicts for one pull job."""
    _require_admin_auth(x_admin_token, x_admin_role, current_user, min_role="superadmin")
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, f"Pull job not found: {job_id}")
        return PullJobResponse(**job)
