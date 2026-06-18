"""
api/routes/auth.py — Authentication routes (register, login, refresh, logout-all).
==================================================================================
"""

from __future__ import annotations

import uuid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_for_storage,
    hash_password,
    validate_phone_number,
    validate_username,
    verify_password,
)
from api.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from db import client as db_client

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(body: RegisterRequest) -> TokenResponse:
    """Register a new user account."""
    try:
        username = validate_username(body.username)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        phone = validate_phone_number(body.phone_number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if db_client.get_user_by_identifier(username):
        raise HTTPException(status_code=409, detail="Username already taken.")
    if db_client.get_user_by_identifier(body.email):
        raise HTTPException(status_code=409, detail="Email already registered.")
    if phone and db_client.get_user_by_identifier(phone):
        raise HTTPException(status_code=409, detail="Phone number already registered.")

    hashed = hash_password(body.password)
    family = uuid.uuid4()

    user = db_client.create_user(
        username=username,
        email=body.email.lower().strip(),
        phone_number=phone,
        password_hash=hashed,
    )

    access = create_access_token(user["id"], user["role"], username=user["username"])
    refresh = create_refresh_token(user["id"], family)

    db_client.update_refresh_token_hash(user["id"], hash_for_storage(refresh), family)

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    """Login a user and return tokens."""
    user = db_client.get_user_by_identifier(body.identifier)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    family = uuid.uuid4()

    access = create_access_token(user["id"], user["role"], username=user["username"])
    refresh = create_refresh_token(user["id"], family)

    db_client.update_refresh_token_hash(user["id"], hash_for_storage(refresh), family)

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(body: RefreshRequest) -> TokenResponse:
    """Rotate the refresh token and return a new token pair."""
    payload = decode_token(body.refresh_token, expected_type="refresh")
    user_id = UUID(payload["sub"])
    family = UUID(payload["family"])

    meta = db_client.get_refresh_token_meta(user_id)
    if not meta or not meta["refresh_token_hash"]:
        raise HTTPException(status_code=401, detail="Token revoked.")

    incoming_hash = hash_for_storage(body.refresh_token)
    if incoming_hash != meta["refresh_token_hash"]:
        db_client.update_refresh_token_hash(user_id, None, None)
        raise HTTPException(status_code=401, detail="Token reuse detected. Session revoked.")

    if str(family) != str(meta["token_family"]):
        raise HTTPException(status_code=401, detail="Invalid token family.")

    new_family = uuid.uuid4()
    user = db_client.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    access = create_access_token(user["id"], user["role"], username=user["username"])
    refresh = create_refresh_token(user["id"], new_family)

    db_client.update_refresh_token_hash(user["id"], hash_for_storage(refresh), new_family)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout-all", status_code=200)
def logout_all(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Revoke all refresh tokens for the current user."""
    db_client.update_refresh_token_hash(current_user["user_id"], None, None)
    return {"detail": "Logged out from all devices."}
