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
from api.schemas import UserMeResponse
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
