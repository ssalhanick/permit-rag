"""
api/routes/auth.py — Auth routes (Cognito-backed).
===================================================
All credential operations (register, login, token refresh) are owned by
Amazon Cognito. This module owns the RDS-side profile: GET /auth/me, which
lazy-provisions the user row on first login, plus the endpoints that let a user
edit their own username and profile photo.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.auth import get_current_user
from api.schemas import (
    DesignIntentRequest,
    DesignIntentResponse,
    SetActiveProjectRequest,
    UpdateUserProfileRequest,
    UpsertRoomScansRequest,
    UserMeResponse,
    UserRoomScanResponse,
)
from db import client as db_client

router = APIRouter(prefix="/auth", tags=["auth"])

# Generous for a 256x256 WebP (~20 KB in practice), tight enough that a
# full-resolution phone photo posted straight at this endpoint is rejected
# rather than buffered. This handler is the ONLY body-size limit in the
# request path — neither the ALB nor uvicorn caps it.
MAX_AVATAR_BYTES = 512 * 1024
_AVATAR_CHUNK_BYTES = 64 * 1024

# Formats the browser can render natively and the user_avatars CHECK accepts.
# HEIC is deliberately absent: it is an accepted *input* format, transcoded to
# WebP client-side by resizeImageToSquare, so it should never arrive here.
_SUPPORTED_AVATAR_FORMATS = "JPEG, PNG, WebP, or HEIC"

_HEIC_BRANDS = frozenset(
    {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}
)


def _sniff_image_mime(head: bytes) -> str | None:
    """Identify an image from its leading bytes, or None if unrecognized.

    Content sniffing rather than trusting UploadFile.content_type, which is
    client-supplied — and, for HEIC, frequently sent as an empty string by
    Chrome, which has no MIME mapping for the extension. Returns "image/heic"
    for HEIC so the caller can reject it with a specific message instead of a
    generic "unsupported file".
    """
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # HEIC/HEIF is ISO-BMFF: a length prefix, then "ftyp", then the brand.
    if head[4:8] == b"ftyp" and head[8:12] in _HEIC_BRANDS:
        return "image/heic"
    return None


async def _read_capped(file: UploadFile) -> bytes:
    """Read an upload into memory, rejecting anything over MAX_AVATAR_BYTES.

    Chunked so an oversized body is abandoned as soon as it crosses the limit
    instead of being fully buffered first.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_AVATAR_CHUNK_BYTES):
        total += len(chunk)
        if total > MAX_AVATAR_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Image too large. The limit is {MAX_AVATAR_BYTES // 1024} KB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _user_me(user: dict) -> UserMeResponse:
    """Build the GET /auth/me payload from a users row.

    Shared by every endpoint that returns the current user so a new profile
    field is a one-line change here rather than an edit at four call sites.
    Expects the row to carry avatar_updated_at — db_client.get_user_by_id and
    update_user_profile both join it in.
    """
    return UserMeResponse(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        role=user["role"],
        cognito_sub=user["cognito_sub"],
        created_at=user["created_at"],
        active_project_id=user.get("active_project_id"),
        has_contractor_profile=db_client.contractor_profile_exists(user["id"]),
        avatar_updated_at=user.get("avatar_updated_at"),
    )


def _require_user(user_id: UUID) -> dict:
    """Load the caller's own row, 404ing if it has gone away mid-session."""
    user = db_client.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@router.get("/me", response_model=UserMeResponse, summary="Get current user profile")
def get_me(current_user: Annotated[dict, Depends(get_current_user)]) -> UserMeResponse:
    """
    Return the authenticated user's profile from RDS.

    On first Cognito login, get_current_user lazily creates the RDS row via
    get_or_create_cognito_user before this handler runs, so the row always exists.
    """
    return _user_me(_require_user(current_user["user_id"]))


@router.patch("/me", response_model=UserMeResponse, summary="Update own profile")
def update_me(
    body: UpdateUserProfileRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> UserMeResponse:
    """Update the caller's own profile fields (currently just the username).

    Usernames start out auto-derived from the email address at first Cognito
    login, so this is what lets a user replace "ssalhanick_a3f2" with something
    they picked. Cognito credentials are untouched — sign-in continues to use
    the email alias, so a rename never locks anyone out.
    """
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return _user_me(_require_user(current_user["user_id"]))
    try:
        updated = db_client.update_user_profile(current_user["user_id"], **fields)
    except psycopg.errors.UniqueViolation as exc:
        # Caught rather than pre-checked with a SELECT: two users claiming the
        # same name concurrently would both pass the check and one would still
        # hit the UNIQUE index. Letting the index arbitrate is race-free.
        raise HTTPException(status_code=409, detail="That username is already taken.") from exc
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    return _user_me(updated)


@router.patch("/me/active-project", response_model=UserMeResponse)
def set_active_project(
    body: SetActiveProjectRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> UserMeResponse:
    """Set (or clear, with project_id=null) the caller's single active project.

    New queries, uploads, and room scans that don't specify a project_id fall
    back to this one. The caller must be a member of the project being activated.
    """
    if body.project_id is not None:
        role = db_client.get_project_role(body.project_id, current_user["user_id"])
        if not role:
            raise HTTPException(status_code=403, detail="Not a member of that project.")
    db_client.set_active_project(current_user["user_id"], body.project_id)
    return _user_me(_require_user(current_user["user_id"]))


@router.post("/me/avatar", response_model=UserMeResponse, summary="Upload profile photo")
async def upload_my_avatar(
    current_user: Annotated[dict, Depends(get_current_user)],
    file: Annotated[UploadFile, File(description="Square image, already resized client-side.")],
) -> UserMeResponse:
    """Store the caller's profile photo.

    The browser resizes to 256x256 and re-encodes to WebP before posting
    (frontend/src/avatarUtils.js), which is also what strips EXIF and converts
    HEIC. This endpoint re-validates independently rather than trusting that:
    the size cap and the magic-byte sniff both assume a caller that skipped the
    client entirely.
    """
    data = await _read_capped(file)
    if not data:
        raise HTTPException(status_code=422, detail="Empty file.")

    mime = _sniff_image_mime(data[:16])
    if mime == "image/heic":
        # Reachable only if the client-side transcode was bypassed. Storing it
        # would mean serving bytes that Chrome and Firefox cannot render.
        raise HTTPException(
            status_code=415,
            detail="HEIC images must be converted before upload. Please try again from the app.",
        )
    if mime is None:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image format. Use {_SUPPORTED_AVATAR_FORMATS}.",
        )

    db_client.set_user_avatar(current_user["user_id"], data, mime)
    return _user_me(_require_user(current_user["user_id"]))


@router.delete("/me/avatar", response_model=UserMeResponse, summary="Remove profile photo")
def delete_my_avatar(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> UserMeResponse:
    """Remove the caller's profile photo, reverting them to initials.

    Idempotent — removing an absent photo is a success, not a 404.
    """
    db_client.clear_user_avatar(current_user["user_id"])
    return _user_me(_require_user(current_user["user_id"]))


@router.get("/me/room-scans", response_model=list[UserRoomScanResponse])
def list_my_room_scans(current_user: Annotated[dict, Depends(get_current_user)]) -> list[dict]:
    """List all room/structure scans in the caller's personal library."""
    rows = db_client.list_user_room_scans(current_user["user_id"])
    return [dict(row) for row in rows]


@router.post("/me/room-scans", response_model=list[UserRoomScanResponse])
def upsert_my_room_scans(
    body: UpsertRoomScansRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> list[dict]:
    """Upsert derived scan summaries into the caller's library (no project link)."""
    for scan in body.scans:
        if "surfaces" in (scan.derived or {}):
            raise HTTPException(status_code=422, detail="Derived summaries must not include surfaces.")
    payload = [scan.model_dump() for scan in body.scans]
    try:
        rows = db_client.upsert_user_room_scans(current_user["user_id"], payload)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return [dict(row) for row in rows]


@router.post(
    "/me/room-scans/{scan_id}/design-intent",
    response_model=DesignIntentResponse,
)
def library_room_design_intent(
    scan_id: UUID,
    body: DesignIntentRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    """Parse remodel intent for a scan in the caller's personal library."""
    from api.design_intent_helpers import _resolve_room_scan_row, run_design_intent

    rows = db_client.list_user_room_scans(current_user["user_id"])
    room_row = _resolve_room_scan_row(rows, scan_id)
    return run_design_intent(
        user_id=current_user["user_id"],
        project_id=None,
        scan_id=scan_id,
        room_row=room_row,
        body=body,
    )
