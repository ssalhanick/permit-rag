"""
tests/test_auth_profile_routes.py — PATCH /auth/me (username) and the avatar
upload/serve endpoints added alongside migration 048.

The db layer is patched throughout; these cover route wiring, validation, and
status-code mapping, not SQL.
"""

from __future__ import annotations

import struct
import zlib
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import auth as auth_route
from api.routes import users as users_route
from api.routes.auth import MAX_AVATAR_BYTES, _sniff_image_mime

client = TestClient(app)

NOW = datetime(2026, 8, 10, 12, 0, 0, tzinfo=UTC)


def _user_row(user_id, username="qa-user", avatar_updated_at=None):
    return {
        "id": user_id,
        "username": username,
        "email": "qa@example.com",
        "role": "member",
        "cognito_sub": "sub-123",
        "created_at": NOW,
        "active_project_id": None,
        "avatar_updated_at": avatar_updated_at,
    }


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


@pytest.fixture
def as_user():
    """Authenticate as a fresh user and stub contractor_profile_exists."""
    user_id = uuid4()
    app.dependency_overrides[auth_route.get_current_user] = lambda: _current_user(user_id)
    with patch.object(auth_route.db_client, "contractor_profile_exists", return_value=False):
        yield user_id
    app.dependency_overrides.clear()


@contextmanager
def _avatar_write_stubbed(user_id, updated_at=NOW):
    """Stub the two db calls a successful avatar write makes.

    Yields the set_user_avatar mock so a test can assert on the mime it stored.
    """
    with (
        patch.object(auth_route.db_client, "set_user_avatar", return_value=updated_at) as mock,
        patch.object(
            auth_route.db_client,
            "get_user_by_id",
            return_value=_user_row(user_id, avatar_updated_at=updated_at),
        ),
    ):
        yield mock


# ── Image fixtures ────────────────────────────────────────────
# Hand-built rather than checked in as binaries: each is the smallest byte
# string that its format's magic-number check accepts.

def _png_bytes(payload_len: int = 0) -> bytes:
    """A PNG signature plus an IHDR chunk, optionally padded to a target size."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr
    chunk += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
    out = sig + chunk
    return out + b"\x00" * max(0, payload_len - len(out))


JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 20
WEBP_BYTES = b"RIFF" + struct.pack("<I", 30) + b"WEBP" + b"VP8 " + b"\x00" * 16
# ISO-BMFF box: 4-byte length, "ftyp", then the HEIC major brand.
HEIC_BYTES = struct.pack(">I", 24) + b"ftyp" + b"heic" + b"\x00" * 12


# ── _sniff_image_mime ─────────────────────────────────────────

@pytest.mark.parametrize(
    "data, expected",
    [
        (JPEG_BYTES, "image/jpeg"),
        (_png_bytes(), "image/png"),
        (WEBP_BYTES, "image/webp"),
        (HEIC_BYTES, "image/heic"),
        (b"%PDF-1.7\n" + b"\x00" * 10, None),
        (b"", None),
        (b"\xff\xd8", None),  # truncated JPEG magic
    ],
)
def test_sniff_image_mime(data, expected) -> None:
    assert _sniff_image_mime(data[:16]) == expected


def test_sniff_rejects_riff_that_is_not_webp() -> None:
    """A RIFF container that is a WAV, not a WebP, must not pass."""
    wav = b"RIFF" + struct.pack("<I", 30) + b"WAVE" + b"\x00" * 16
    assert _sniff_image_mime(wav[:16]) is None


# ── PATCH /auth/me ────────────────────────────────────────────

def test_update_username_succeeds(as_user) -> None:
    updated = _user_row(as_user, username="scott")
    with patch.object(auth_route.db_client, "update_user_profile", return_value=updated) as mock:
        resp = client.patch("/api/auth/me", json={"username": "scott"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "scott"
    mock.assert_called_once_with(as_user, username="scott")


def test_update_username_is_lowercased(as_user) -> None:
    """Mixed case is normalized before it reaches the DB, per migration 011."""
    with patch.object(
        auth_route.db_client, "update_user_profile", return_value=_user_row(as_user, "scott")
    ) as mock:
        resp = client.patch("/api/auth/me", json={"username": "ScoTT"})
    assert resp.status_code == 200
    mock.assert_called_once_with(as_user, username="scott")


def test_update_username_conflict_returns_409(as_user) -> None:
    with patch.object(
        auth_route.db_client,
        "update_user_profile",
        side_effect=psycopg.errors.UniqueViolation("duplicate key"),
    ):
        resp = client.patch("/api/auth/me", json={"username": "taken"})
    assert resp.status_code == 409
    assert "taken" in resp.json()["detail"].lower()


@pytest.mark.parametrize(
    "username",
    [
        "ab",                    # under min_length
        "a" * 31,                # over max_length
        "has spaces",
        "has@symbol",
        "emoji\U0001f600",
        "___",                   # punctuation only, no letter or digit
    ],
)
def test_update_username_rejects_invalid(as_user, username) -> None:
    resp = client.patch("/api/auth/me", json={"username": username})
    assert resp.status_code == 422


def test_update_with_empty_body_is_a_noop(as_user) -> None:
    """No fields set should return the current profile, not write anything."""
    with (
        patch.object(auth_route.db_client, "get_user_by_id", return_value=_user_row(as_user)),
        patch.object(auth_route.db_client, "update_user_profile") as mock,
    ):
        resp = client.patch("/api/auth/me", json={})
    assert resp.status_code == 200
    mock.assert_not_called()


def test_me_exposes_avatar_updated_at(as_user) -> None:
    with patch.object(
        auth_route.db_client, "get_user_by_id", return_value=_user_row(as_user, avatar_updated_at=NOW)
    ):
        resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["avatar_updated_at"] is not None


# ── POST /auth/me/avatar ──────────────────────────────────────

def test_upload_avatar_succeeds(as_user) -> None:
    with _avatar_write_stubbed(as_user) as mock:
        resp = client.post(
            "/api/auth/me/avatar",
            files={"file": ("avatar.webp", WEBP_BYTES, "image/webp")},
        )
    assert resp.status_code == 200
    assert resp.json()["avatar_updated_at"] is not None
    assert mock.call_args[0][2] == "image/webp"


def test_upload_avatar_trusts_magic_bytes_over_content_type(as_user) -> None:
    """A real JPEG sent with an empty content_type is accepted.

    Browsers send no MIME for some picker results, so requiring content_type
    would reject legitimate uploads.
    """
    with _avatar_write_stubbed(as_user) as mock:
        resp = client.post(
            "/api/auth/me/avatar",
            files={"file": ("photo", JPEG_BYTES, "")},
        )
    assert resp.status_code == 200
    assert mock.call_args[0][2] == "image/jpeg"


def test_upload_avatar_rejects_disguised_text_file(as_user) -> None:
    """A .png name and an image/png content_type do not make it an image."""
    resp = client.post(
        "/api/auth/me/avatar",
        files={"file": ("evil.png", b"#!/bin/sh\nrm -rf /\n", "image/png")},
    )
    assert resp.status_code == 415


def test_upload_avatar_rejects_heic_with_a_specific_message(as_user) -> None:
    """HEIC should have been transcoded client-side; say so rather than 'unsupported'."""
    resp = client.post(
        "/api/auth/me/avatar",
        files={"file": ("photo.heic", HEIC_BYTES, "image/heic")},
    )
    assert resp.status_code == 415
    assert "heic" in resp.json()["detail"].lower()


def test_upload_avatar_rejects_oversized(as_user) -> None:
    oversized = _png_bytes(MAX_AVATAR_BYTES + 1024)
    resp = client.post(
        "/api/auth/me/avatar",
        files={"file": ("big.png", oversized, "image/png")},
    )
    assert resp.status_code == 413


def test_upload_avatar_accepts_size_at_the_limit(as_user) -> None:
    """The cap is inclusive — exactly MAX_AVATAR_BYTES must not 413."""
    at_limit = _png_bytes(MAX_AVATAR_BYTES)
    with _avatar_write_stubbed(as_user):
        resp = client.post(
            "/api/auth/me/avatar",
            files={"file": ("big.png", at_limit, "image/png")},
        )
    assert resp.status_code == 200


def test_upload_avatar_rejects_empty_file(as_user) -> None:
    resp = client.post("/api/auth/me/avatar", files={"file": ("empty.png", b"", "image/png")})
    assert resp.status_code == 422


# ── DELETE /auth/me/avatar ────────────────────────────────────

def test_delete_avatar_is_idempotent(as_user) -> None:
    """Removing a photo that isn't there succeeds and reports no avatar."""
    with (
        patch.object(auth_route.db_client, "clear_user_avatar", return_value=False),
        patch.object(auth_route.db_client, "get_user_by_id", return_value=_user_row(as_user)),
    ):
        resp = client.delete("/api/auth/me/avatar")
    assert resp.status_code == 200
    assert resp.json()["avatar_updated_at"] is None


# ── GET /users/{user_id}/avatar ───────────────────────────────

def test_get_avatar_returns_image_with_cache_headers() -> None:
    user_id = uuid4()
    avatar = {"data": WEBP_BYTES, "mime": "image/webp", "updated_at": NOW}
    with patch.object(users_route.db_client, "get_user_avatar", return_value=avatar):
        resp = client.get(f"/api/users/{user_id}/avatar")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/webp"
    assert resp.content == WEBP_BYTES
    assert "max-age" in resp.headers["cache-control"]
    assert resp.headers["etag"]


def test_get_avatar_honors_if_none_match() -> None:
    """A client with the current ETag gets a 304 and no body."""
    user_id = uuid4()
    avatar = {"data": WEBP_BYTES, "mime": "image/webp", "updated_at": NOW}
    with patch.object(users_route.db_client, "get_user_avatar", return_value=avatar):
        first = client.get(f"/api/users/{user_id}/avatar")
        second = client.get(
            f"/api/users/{user_id}/avatar",
            headers={"If-None-Match": first.headers["etag"]},
        )
    assert second.status_code == 304
    assert second.content == b""


def test_get_avatar_etag_changes_when_photo_is_replaced() -> None:
    """Otherwise a re-upload would keep serving the old image from cache."""
    user_id = uuid4()
    later = datetime(2026, 8, 10, 13, 0, 0, tzinfo=UTC)
    with patch.object(
        users_route.db_client,
        "get_user_avatar",
        return_value={"data": WEBP_BYTES, "mime": "image/webp", "updated_at": NOW},
    ):
        first = client.get(f"/api/users/{user_id}/avatar")
    with patch.object(
        users_route.db_client,
        "get_user_avatar",
        return_value={"data": JPEG_BYTES, "mime": "image/jpeg", "updated_at": later},
    ):
        second = client.get(f"/api/users/{user_id}/avatar")
    assert first.headers["etag"] != second.headers["etag"]


def test_get_avatar_404_when_unset() -> None:
    with patch.object(users_route.db_client, "get_user_avatar", return_value=None):
        resp = client.get(f"/api/users/{uuid4()}/avatar")
    assert resp.status_code == 404


def test_get_avatar_needs_no_authentication() -> None:
    """An <img> tag cannot send a bearer token — this must work unauthenticated."""
    assert not app.dependency_overrides
    avatar = {"data": WEBP_BYTES, "mime": "image/webp", "updated_at": NOW}
    with patch.object(users_route.db_client, "get_user_avatar", return_value=avatar):
        resp = client.get(f"/api/users/{uuid4()}/avatar")
    assert resp.status_code == 200
