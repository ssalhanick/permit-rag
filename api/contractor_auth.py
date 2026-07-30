"""
api/contractor_auth.py — Contractor-side authorization dependencies.
======================================================================
Gates contractor-only routes on contractor_profiles row existence, not a
Cognito group. users.role (member/admin/superadmin) is a staff/ops axis
(docs/cognito_groups_rbac.md) — orthogonal to "is this user also a
contractor" — and a Cognito-group change only takes effect on the next
token refresh, a poor fit for "I just signed up, let me in now."
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from api.auth import get_current_user
from db import client as db_client

CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_contractor_profile(current_user: CurrentUser) -> dict:
    """403 if the caller has no contractor_profiles row. Returns the profile row."""
    profile = db_client.get_contractor_profile_by_user(current_user["user_id"])
    if not profile:
        raise HTTPException(status_code=403, detail="A contractor profile is required.")
    return profile


def require_biddable_contractor(current_user: CurrentUser) -> dict:
    """403 if the caller has no profile, or no non-expired license on file."""
    profile = require_contractor_profile(current_user)
    if not db_client.has_valid_license(profile["id"]):
        raise HTTPException(
            status_code=403,
            detail="A current, non-expired license is required to bid.",
        )
    return profile
