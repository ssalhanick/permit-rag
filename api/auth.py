"""
api/auth.py — JWT, password hashing, and user identifier validation.
=====================================================================
All authentication and authorization primitives live here.
No other module may issue token operations (see AGENTS.md).
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated, Optional
from uuid import UUID

import jwt
import phonenumbers
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

# Username validation regexes
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]{1,28}[a-z0-9]$")
_CONSECUTIVE_SPECIAL_RE = re.compile(r"[_\.\-]{2,}")

_RESERVED_USERNAMES: frozenset[str] = frozenset({
    "api", "auth", "login", "logout", "register", "me", "self",
    "admin", "administrator", "root", "superuser", "system", "service",
    "null", "undefined", "true", "false", "none",
    "support", "help", "billing", "security", "abuse", "noreply",
    "permitrag", "permit_rag", "permit.rag",
})


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with Argon2id. Returns the encoded hash."""
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True if plaintext matches the Argon2id hash."""
    try:
        return _ph.verify(hashed, plaintext)
    except VerifyMismatchError:
        return False


def hash_for_storage(token: str) -> str:
    """Return SHA-256 hex digest of a token for secure database storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def validate_username(raw: str) -> str:
    """Normalize and validate a username. Returns lowercase value or raises ValueError."""
    username = raw.strip().lower()
    if not _USERNAME_RE.match(username):
        raise ValueError(
            "Username must be 3-30 characters, start and end with a letter or digit, "
            "and contain only letters, digits, underscores, dots, or hyphens."
        )
    if _CONSECUTIVE_SPECIAL_RE.search(username):
        raise ValueError("Username may not contain consecutive special characters.")
    if username in _RESERVED_USERNAMES:
        raise ValueError(f"Username '{username}' is reserved.")
    return username


def validate_phone_number(raw: Optional[str]) -> Optional[str]:
    """Validate and format phone number to E.164. Returns formatted string or raises ValueError."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw.strip(), "US")
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number structure.")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except Exception as exc:
        raise ValueError(f"Invalid phone number format: {exc}") from exc


def _jwt_secret() -> str:
    secret = os.environ.get("API_JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("API_JWT_SECRET must be at least 32 characters.")
    return secret


def create_access_token(user_id: UUID, role: str, username: str | None = None) -> str:
    """Mint a short-lived JWT access token for user_id."""
    ttl = int(os.environ.get("API_JWT_ACCESS_TTL_MIN", "15"))
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=ttl),
    }
    if username:
        payload["username"] = username
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def create_refresh_token(user_id: UUID, family: UUID) -> str:
    """Mint a long-lived refresh token with token family."""
    ttl = int(os.environ.get("API_JWT_REFRESH_TTL_DAYS", "7"))
    payload = {
        "sub": str(user_id),
        "family": str(family),
        "type": "refresh",
        "exp": datetime.now(UTC) + timedelta(days=ttl),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def decode_token(token: str, expected_type: str = "access") -> dict:
    """Decode and validate a JWT. Raises HTTPException 401 on failure."""
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Wrong token type.")
    return payload


def get_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer)
    ] = None,
) -> dict:
    """FastAPI dependency: extract + validate access token from Bearer header."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    payload = decode_token(credentials.credentials, expected_type="access")
    res = {"user_id": UUID(payload["sub"]), "role": payload["role"]}
    if "username" in payload:
        res["username"] = payload["username"]
    return res


def get_optional_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(_bearer)
    ] = None,
) -> dict | None:
    """FastAPI dependency: extract + validate access token if present, return None if missing or invalid."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        res = {"user_id": UUID(payload["sub"]), "role": payload["role"]}
        if "username" in payload:
            res["username"] = payload["username"]
        return res
    except Exception:
        return None
