"""
tests/test_sprint9.py — Cognito Auth & Projects regression tests (Sprint 11 update)
====================================================================================
Auth primitive tests (Argon2id, custom JWT) removed — Cognito owns credentials.
Retained: TestCognitoVerification, TestProjectsAPI, TestQueryHistoryAPI.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth import verify_cognito_token, get_current_user
from api.main import app
from db import client as db_client


# ═══════════════════════════════════════════════════════════════
#  Helpers — build a fake RS256-signed Cognito token for tests
# ═══════════════════════════════════════════════════════════════

def _make_cognito_payload(sub: str = None, email: str = "test@example.com", region: str = "us-east-1", pool_id: str = "us-east-1_TESTPOOL") -> dict:
    """Return a minimal Cognito idToken payload."""
    return {
        "sub": sub or str(uuid4()),
        "email": email,
        "iss": f"https://cognito-idp.{region}.amazonaws.com/{pool_id}",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "token_use": "id",
    }


# ═══════════════════════════════════════════════════════════════
#  Unit Tests — Cognito token verification
# ═══════════════════════════════════════════════════════════════

class TestCognitoVerification:
    """verify_cognito_token() JWKS verification logic."""

    def test_missing_kid_header_raises(self):
        """A token without a kid header must raise HTTP 401."""
        from jose import jwt as jose_jwt
        import base64, json as _json

        # Build a token without a kid in the header
        # We can't sign with a real RS256 key in unit tests, so mock _get_jwks_key
        # and test the kid-missing path directly by patching jwt.get_unverified_headers.
        with patch("api.auth.jwt.get_unverified_headers", return_value={}):
            with pytest.raises(HTTPException) as exc:
                verify_cognito_token("fake.token.here")
            assert exc.value.status_code == 401
            assert "kid" in exc.value.detail

    def test_unknown_kid_raises(self, monkeypatch):
        """A token with a kid not in the JWKS cache must raise HTTP 401."""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TESTPOOL")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")

        with patch("api.auth.jwt.get_unverified_headers", return_value={"kid": "unknown-kid"}):
            with patch("api.auth._fetch_jwks") as mock_fetch:
                # After fetch, cache is still empty — kid not found
                mock_fetch.side_effect = lambda: None
                import api.auth as auth_mod
                auth_mod._jwks_cache = {}
                with pytest.raises(HTTPException) as exc:
                    verify_cognito_token("fake.token.here")
                assert exc.value.status_code == 401

    def test_invalid_signature_raises(self, monkeypatch):
        """A token with a mismatched signature must raise HTTP 401."""
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TESTPOOL")
        monkeypatch.setenv("COGNITO_REGION", "us-east-1")

        fake_key = {"kid": "test-kid", "kty": "RSA", "n": "bogus", "e": "AQAB"}
        with patch("api.auth.jwt.get_unverified_headers", return_value={"kid": "test-kid"}):
            with patch("api.auth._get_jwks_key", return_value=fake_key):
                with patch("api.auth.jwt.decode", side_effect=Exception("bad sig")):
                    with pytest.raises(HTTPException) as exc:
                        verify_cognito_token("bad.token.value")
                    assert exc.value.status_code == 401


# ═══════════════════════════════════════════════════════════════
#  Auth fixture — produces a mock Cognito-shaped Bearer token
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def auth_headers(monkeypatch):
    """
    Bypass full Cognito JWT verification for integration tests by patching
    get_current_user to return a fixed user dict.
    """
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TESTPOOL")
    monkeypatch.setenv("COGNITO_REGION", "us-east-1")

    uid = uuid4()
    fake_user = {
        "user_id": uid,
        "role": "member",
        "cognito_sub": str(uuid4()),
        "username": "test_user",
        "email": "test@example.com",
        "created_at": datetime.now(timezone.utc),
    }

    def _fake_get_current_user(credentials=None):
        return fake_user

    monkeypatch.setattr("api.routes.projects.get_current_user", _fake_get_current_user)
    monkeypatch.setattr("api.routes.query.get_current_user", _fake_get_current_user)

    return {
        "Authorization": "Bearer fake-cognito-token",
        "User-Id": str(uid),
        "_uid": uid,
        "_user": fake_user,
    }


# ═══════════════════════════════════════════════════════════════
#  Integration/Mock Tests — Projects & Sharing Routes
# ═══════════════════════════════════════════════════════════════

class TestProjectsAPI:
    """Project CRUD, sharing, and RBAC membership controls."""

    def test_create_project(self, auth_headers, monkeypatch):
        """POST /projects establishes owner and returns project representation."""
        uid = auth_headers["_uid"]

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
        uid = auth_headers["_uid"]

        monkeypatch.setattr(db_client, "get_project_role", lambda p, u: "owner" if u == uid else None)

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
        uid = auth_headers["_uid"]

        monkeypatch.setattr(db_client, "get_project_role", lambda p, u: "viewer" if u == uid else None)

        client = TestClient(app)
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
        uid = auth_headers["_uid"]

        monkeypatch.setattr(db_client, "get_project_role", lambda p, u: "editor" if u == uid else None)
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


# ═══════════════════════════════════════════════════════════════
#  Integration/Mock Tests — Query History Routes
# ═══════════════════════════════════════════════════════════════

class TestQueryHistoryAPI:
    """GET /query/history and DELETE /query/history/{query_id}."""

    def test_get_query_history_success(self, auth_headers, monkeypatch):
        uid = auth_headers["_uid"]
        mock_history = [
            {
                "id": uuid4(),
                "user_id": uid,
                "query_text": "How high can a fence be?",
                "answer_text": "Up to 6 feet.",
                "created_at": datetime.now(timezone.utc),
            }
        ]
        monkeypatch.setattr(
            db_client,
            "get_user_query_history",
            lambda u, project_id=None: mock_history if u == uid else [],
        )

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
        uid = auth_headers["_uid"]
        qid = uuid4()
        monkeypatch.setattr(
            db_client,
            "delete_user_query",
            lambda u, q: True if (u == uid and q == qid) else False,
        )

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
