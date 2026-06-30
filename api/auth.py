"""
api/auth.py — Cognito JWT verification and FastAPI auth dependencies.
=====================================================================
Verifies RS256 JWTs issued by Amazon Cognito via cached JWKS endpoint.
No password hashing or token minting — Cognito owns all credential operations.
"""

from __future__ import annotations

import os
import time
from typing import Annotated
from uuid import UUID

import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_bearer = HTTPBearer(auto_error=False)

# JWKS key cache: {kid: jwk_dict}, refreshed on unknown kid or TTL expiry.
_jwks_cache: dict[str, dict] = {}
_jwks_last_fetched: float = 0.0
_JWKS_TTL: float = 3600.0  # re-fetch at most once per hour


# ── Environment helpers ───────────────────────────────────────


def _pool_id() -> str:
    """Return Cognito User Pool ID from env."""
    pool_id = os.environ.get("COGNITO_USER_POOL_ID", "")
    if not pool_id:
        raise RuntimeError("COGNITO_USER_POOL_ID env var is required.")
    return pool_id


def _region() -> str:
    """Return AWS region from env (defaults to us-east-1)."""
    return os.environ.get("COGNITO_REGION", "us-east-1")



def _jwks_url() -> str:
    """Build the Cognito JWKS endpoint URL."""
    return (
        f"https://cognito-idp.{_region()}.amazonaws.com"
        f"/{_pool_id()}/.well-known/jwks.json"
    )


# ── JWKS fetching and caching ─────────────────────────────────


def _fetch_jwks() -> None:
    """Fetch fresh JWKS keys from Cognito and populate the cache."""
    global _jwks_cache, _jwks_last_fetched
    try:
        resp = requests.get(_jwks_url(), timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to fetch Cognito JWKS: {exc}",
        ) from exc
    keys = resp.json().get("keys", [])
    _jwks_cache = {k["kid"]: k for k in keys}
    _jwks_last_fetched = time.monotonic()


def _get_jwks_key(kid: str) -> dict:
    """Return the JWK dict for the given kid, refreshing the cache if needed."""
    stale = time.monotonic() - _jwks_last_fetched > _JWKS_TTL
    if kid not in _jwks_cache or stale:
        _fetch_jwks()
    if kid not in _jwks_cache:
        raise HTTPException(status_code=401, detail="Unknown token signing key.")
    return _jwks_cache[kid]


# ── Token verification ────────────────────────────────────────


def verify_cognito_token(token: str) -> dict:
    """Decode and verify a Cognito-issued RS256 JWT. Returns the payload dict."""
    try:
        headers = jwt.get_unverified_headers(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token headers.")

    kid = headers.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Token missing kid header.")

    key = _get_jwks_key(kid)
    issuer = f"https://cognito-idp.{_region()}.amazonaws.com/{_pool_id()}"

    # RS256 signature + issuer together prove the token came from our pool.
    # Audience verification (app client ID) is skipped here; add COGNITO_APP_CLIENT_ID
    # to env and pass audience=os.environ["COGNITO_APP_CLIENT_ID"] if stricter checking
    # is required in the future.
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_at_hash": False, "verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {exc}")

    return payload


# ── Internal user extraction ──────────────────────────────────


def _extract_user(credentials: HTTPAuthorizationCredentials | None) -> dict | None:
    """
    Verify credentials, get-or-create the RDS user row, and return a user info dict.
    Returns None on any failure (missing header, bad token, DB error).
    """
    if credentials is None:
        return None
    try:
        payload = verify_cognito_token(credentials.credentials)
    except HTTPException:
        return None

    cognito_sub = payload.get("sub")
    if not cognito_sub:
        return None

    try:
        from db import client as db_client  # late import — avoids circular dep at module load

        user = db_client.get_or_create_cognito_user(
            cognito_sub=cognito_sub,
            email=payload.get("email", ""),
            display_name=payload.get("name") or payload.get("preferred_username"),
        )
    except Exception:
        return None

    return {
        "user_id": user["id"],
        "role": user["role"],
        "cognito_sub": cognito_sub,
        "username": user.get("username"),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
    }


# ── FastAPI dependencies ──────────────────────────────────────


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> dict:
    """FastAPI dependency: verify Cognito token, provision RDS user. Raises 401 on failure."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authorization header missing.")
    payload = verify_cognito_token(credentials.credentials)
    cognito_sub = payload.get("sub")
    if not cognito_sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim.")

    from db import client as db_client

    try:
        user = db_client.get_or_create_cognito_user(
            cognito_sub=cognito_sub,
            email=payload.get("email", ""),
            display_name=payload.get("name") or payload.get("preferred_username"),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database error provisioning user: {exc}",
        ) from exc
    return {
        "user_id": user["id"],
        "role": user["role"],
        "cognito_sub": cognito_sub,
        "username": user.get("username"),
        "email": user.get("email"),
        "created_at": user.get("created_at"),
    }


def get_optional_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> dict | None:
    """FastAPI dependency: verify Cognito token if present; return None if missing or invalid."""
    return _extract_user(credentials)
