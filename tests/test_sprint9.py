"""
tests/test_sprint9.py — Sprint 9 Auth & Projects regression tests
==================================================================
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_for_storage,
    hash_password,
    validate_phone_number,
    validate_username,
    verify_password,
)
from api.main import app
from db import client as db_client


# ═══════════════════════════════════════════════════════════════
#  Unit Tests — Auth & Validation Primitives
# ═══════════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Argon2id hashing and verification logic."""

    def test_hash_and_verify_roundtrip(self):
        """Plaintext password must successfully hash and verify."""
        pw = "superSecretPassword123!"
        hashed = hash_password(pw)
        assert hashed.startswith("$argon2id$")
        assert verify_password(pw, hashed) is True
        assert verify_password("wrong_password", hashed) is False


class TestUsernameValidation:
    """Strict rules for username validation."""

    def test_valid_usernames(self):
        """Usernames meeting character/length/structure rules must pass."""
        for name in ["user123", "alice_bob", "c-d-e", "bob.johnson"]:
            assert validate_username(name) == name

    def test_reserved_usernames_raise(self):
        """Usernames in the reserved set must fail."""
        for name in ["admin", "root", "null", "api", "auth", "permit_rag"]:
            with pytest.raises(ValueError, match="reserved"):
                validate_username(name)

    def test_consecutive_special_chars_raise(self):
        """Consecutive special characters are blocked for visual safety."""
        for name in ["user__admin", "alice..bob", "ch--arlie", "user._name"]:
            with pytest.raises(ValueError, match="consecutive"):
                validate_username(name)

    def test_length_boundaries_raise(self):
        """Too short (<3) or too long (>30) usernames must fail."""
        with pytest.raises(ValueError, match="3-30"):
            validate_username("ab")
        with pytest.raises(ValueError, match="3-30"):
            validate_username("a" * 31)

    def test_invalid_start_or_end_raise(self):
        """Usernames must start and end with an alphanumeric character."""
        for name in ["_username", ".username", "-username", "username_", "username.", "username-"]:
            with pytest.raises(ValueError, match="start and end"):
                validate_username(name)

    def test_case_and_strip_normalization(self):
        """Usernames must be normalized to lowercase and stripped of outer whitespace."""
        assert validate_username("  AlIcE_BoB  ") == "alice_bob"


class TestPhoneValidation:
    """E.164 phone number optional validation."""

    def test_valid_phone_formats(self):
        """E.164 conversion of valid local and international numbers."""
        assert validate_phone_number("2145550100") == "+12145550100"
        assert validate_phone_number("  +1 214-555-0100  ") == "+12145550100"
        assert validate_phone_number(None) is None
        assert validate_phone_number("") is None

    def test_invalid_phone_raises(self):
        """Invalid phone structures must raise ValueError."""
        for num in ["123", "abc-def-ghij", "+1 234"]:
            with pytest.raises(ValueError):
                validate_phone_number(num)


class TestJWTTokens:
    """JWT creation, expiration, and validation."""

    @pytest.fixture(autouse=True)
    def _mock_env(self, monkeypatch):
        monkeypatch.setenv("API_JWT_SECRET", "super-secret-key-at-least-32-chars-long")
        monkeypatch.setenv("API_JWT_ACCESS_TTL_MIN", "15")
        monkeypatch.setenv("API_JWT_REFRESH_TTL_DAYS", "7")

    def test_access_token_claims(self):
        """Access token must contain sub, role, type, and exp."""
        uid = uuid4()
        token = create_access_token(uid, "member")
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == str(uid)
        assert payload["role"] == "member"
        assert payload["type"] == "access"

    def test_refresh_token_claims(self):
        """Refresh token must contain sub, family, type, and exp."""
        uid = uuid4()
        fam = uuid4()
        token = create_refresh_token(uid, fam)
        payload = decode_token(token, expected_type="refresh")
        assert payload["sub"] == str(uid)
        assert payload["family"] == str(fam)
        assert payload["type"] == "refresh"

    def test_wrong_type_raises(self):
        """Decoding access token as refresh must raise HTTP 401."""
        uid = uuid4()
        token = create_access_token(uid, "member")
        with pytest.raises(HTTPException) as exc:
            decode_token(token, expected_type="refresh")
        assert exc.value.status_code == 401
        assert "Wrong token type" in exc.value.detail


# ═══════════════════════════════════════════════════════════════
#  Integration Tests — FastAPI Auth & Refresh Routes
# ═══════════════════════════════════════════════════════════════

class TestAuthAPI:
    """POST /auth/register, /auth/login, /auth/refresh, /auth/logout-all."""

    @pytest.fixture(autouse=True)
    def _mock_env(self, monkeypatch):
        monkeypatch.setenv("API_JWT_SECRET", "super-secret-key-at-least-32-chars-long")

    def test_register_flow(self, monkeypatch):
        """Register route validates input, records user, and returns token response."""
        user_db = {}

        def _fake_create_user(*, username, email, phone_number, password_hash, role="member"):
            user = {
                "id": uuid4(),
                "username": username,
                "email": email,
                "phone_number": phone_number,
                "password_hash": password_hash,
                "role": role,
            }
            user_db[username] = user
            return user

        def _fake_get_user_by_identifier(identifier):
            return user_db.get(identifier.lower())

        monkeypatch.setattr(db_client, "create_user", _fake_create_user)
        monkeypatch.setattr(db_client, "get_user_by_identifier", _fake_get_user_by_identifier)
        monkeypatch.setattr(db_client, "update_refresh_token_hash", lambda *a, **k: None)

        client = TestClient(app)
        response = client.post(
            "/auth/register",
            json={
                "username": "bob_builder",
                "password": "strongPassword123!",
                "email": "bob@example.com",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_login_flow(self, monkeypatch):
        """Login route validates matching credentials."""
        pw_hash = hash_password("pass1234567")
        user = {
            "id": uuid4(),
            "username": "tester",
            "email": "tester@test.com",
            "password_hash": pw_hash,
            "role": "member",
        }

        monkeypatch.setattr(db_client, "get_user_by_identifier", lambda ident: user if ident == "tester" else None)
        monkeypatch.setattr(db_client, "update_refresh_token_hash", lambda *a, **k: None)

        client = TestClient(app)
        # Success
        resp = client.post("/auth/login", json={"identifier": "tester", "password": "pass1234567"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

        # Failure
        resp = client.post("/auth/login", json={"identifier": "tester", "password": "wrongpassword"})
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════
#  Integration/Mock Tests — Projects & Sharing Routes
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def auth_headers(monkeypatch):
    monkeypatch.setenv("API_JWT_SECRET", "super-secret-key-at-least-32-chars-long")
    uid = uuid4()
    token = create_access_token(uid, "member")
    return {"Authorization": f"Bearer {token}", "User-Id": str(uid)}


class TestProjectsAPI:
    """Project CRUD, sharing, and RBAC membership controls."""

    def test_create_project(self, auth_headers, monkeypatch):
        """POST /projects establishes owner and returns project representation."""
        uid = UUID(auth_headers["User-Id"])

        def _fake_create(*, name, owner_user_id, description=None, municipality=None):
            return {
                "id": uuid4(),
                "name": name,
                "owner_user_id": owner_user_id,
                "description": description,
                "municipality": municipality,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }

        monkeypatch.setattr(db_client, "create_project", _fake_create)

        client = TestClient(app)
        resp = client.post(
            "/projects/",
            headers={"Authorization": auth_headers["Authorization"]},
            json={"name": "Pool Project", "municipality": "dallas"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Pool Project"
        assert body["owner_user_id"] == str(uid)

    def test_project_ownership_transfer(self, auth_headers, monkeypatch):
        """Owner role can transfer project ownership to another user."""
        pid = uuid4()
        new_owner_uid = uuid4()
        uid = UUID(auth_headers["User-Id"])

        # Mock role check: current user is owner
        monkeypatch.setattr(db_client, "get_project_role", lambda p, u: "owner" if u == uid else None)
        # Mock actual transfer
        def _fake_transfer(project_id, new_owner_id):
            return {
                "id": project_id,
                "name": "Transferred Project",
                "owner_user_id": new_owner_id,
                "is_active": True,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        monkeypatch.setattr(db_client, "transfer_project_ownership", _fake_transfer)

        client = TestClient(app)
        resp = client.post(
            f"/projects/{pid}/transfer",
            headers={"Authorization": auth_headers["Authorization"]},
            json={"new_owner_id": str(new_owner_uid)},
        )
        assert resp.status_code == 200
        assert resp.json()["owner_user_id"] == str(new_owner_uid)

    def test_project_role_enforcement(self, auth_headers, monkeypatch):
        """Endpoint raises 403 Forbidden when caller role does not qualify."""
        pid = uuid4()
        uid = UUID(auth_headers["User-Id"])

        # Caller is only a viewer
        monkeypatch.setattr(db_client, "get_project_role", lambda p, u: "viewer" if u == uid else None)

        client = TestClient(app)
        # Viewer tries to archive project (requires owner)
        resp = client.delete(
            f"/projects/{pid}",
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 403
        assert "Insufficient project privileges" in resp.json()["detail"]

    def test_document_sharing_success(self, auth_headers, monkeypatch):
        """POST /projects/{id}/documents stores a shared registry record."""
        pid = uuid4()
        did = uuid4()
        uid = UUID(auth_headers["User-Id"])

        # Caller is editor (allowed to share)
        monkeypatch.setattr(db_client, "get_project_role", lambda p, u: "editor" if u == uid else None)
        # Mock document exists
        monkeypatch.setattr(db_client, "get_document_by_uuid", lambda d: {"id": d} if d == did else None)
        monkeypatch.setattr(
            db_client,
            "share_document_to_project",
            lambda project_id, document_id, added_by: {
                "project_id": project_id,
                "document_id": document_id,
                "added_by": added_by,
            },
        )

        client = TestClient(app)
        resp = client.post(
            f"/projects/{pid}/documents",
            headers={"Authorization": auth_headers["Authorization"]},
            json={"document_id": str(did)},
        )
        assert resp.status_code == 201
        assert resp.json()["document_id"] == str(did)


class TestQueryHistoryAPI:
    """GET /query/history and DELETE /query/history/{query_id}."""

    def test_get_query_history_success(self, auth_headers, monkeypatch):
        uid = UUID(auth_headers["User-Id"])
        mock_history = [
            {
                "id": uuid4(),
                "user_id": uid,
                "query_text": "How high can a fence be?",
                "answer_text": "Up to 6 feet.",
                "created_at": datetime.now(timezone.utc),
            }
        ]
        monkeypatch.setattr(db_client, "get_user_query_history", lambda u: mock_history if u == uid else [])

        client = TestClient(app)
        resp = client.get(
            "/query/history",
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["query_text"] == "How high can a fence be?"

    def test_delete_query_history_success(self, auth_headers, monkeypatch):
        uid = UUID(auth_headers["User-Id"])
        qid = uuid4()
        monkeypatch.setattr(db_client, "delete_user_query", lambda u, q: True if (u == uid and q == qid) else False)

        client = TestClient(app)
        resp = client.delete(
            f"/query/history/{qid}",
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 200
        assert resp.json()["detail"] == "Query log entry deleted successfully."

    def test_delete_query_history_unauthorized(self, auth_headers, monkeypatch):
        qid = uuid4()
        monkeypatch.setattr(db_client, "delete_user_query", lambda u, q: False)

        client = TestClient(app)
        resp = client.delete(
            f"/query/history/{qid}",
            headers={"Authorization": auth_headers["Authorization"]},
        )
        assert resp.status_code == 404

