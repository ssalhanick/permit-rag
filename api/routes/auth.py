"""
api/routes/auth.py — Auth routes (Cognito-backed).
===================================================
All credential operations (register, login, token refresh) are owned by
Amazon Cognito. This module provides only GET /auth/me, which lazy-provisions
the RDS user row on first login and returns the user profile.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.schemas import (
    DesignIntentRequest,
    DesignIntentResponse,
    UserMeResponse,
    UpsertRoomScansRequest,
    UserRoomScanResponse,
)
from db import client as db_client

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserMeResponse, summary="Get current user profile")
def get_me(current_user: Annotated[dict, Depends(get_current_user)]) -> UserMeResponse:
    """
    Return the authenticated user's profile from RDS.

    On first Cognito login, get_current_user lazily creates the RDS row via
    get_or_create_cognito_user before this handler runs, so the row always exists.
    """
    user = db_client.get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserMeResponse(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        role=user["role"],
        cognito_sub=user["cognito_sub"],
        created_at=user["created_at"],
    )


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
    rows = db_client.upsert_user_room_scans(current_user["user_id"], payload)
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
