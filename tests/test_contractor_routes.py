"""
tests/test_contractor_routes.py — /contractors/* route behavior.

Same TestClient + app.dependency_overrides + patch.object(db_client, ...) pattern
as test_project_jurisdiction_routes.py — no real database involved.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.contractor_auth import require_contractor_profile
from api.main import app
from api.routes import contractors as contractors_route

client = TestClient(app)


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-contractor"}


def _profile_row(profile_id, user_id, **overrides):
    now = datetime.now(UTC)
    row = {
        "id": profile_id,
        "user_id": user_id,
        "business_name": "Acme Roofing",
        "contact_name": None,
        "phone": None,
        "trades": ["Roofing"],
        "service_municipalities": ["dallas"],
        "bio": None,
        "years_in_business": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


def _license_row(license_id, profile_id, **overrides):
    now = datetime.now(UTC)
    row = {
        "id": license_id,
        "contractor_profile_id": profile_id,
        "trade": "Roofing",
        "license_number": "TX12345",
        "issuing_authority": None,
        "expiration_date": "2028-01-01",
        "insurance_provider": None,
        "insurance_policy_number": None,
        "insurance_coverage_amount": None,
        "insurance_expiration_date": None,
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


# ── profile ───────────────────────────────────────────────────────


def test_create_profile_success() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(contractors_route.db_client, "contractor_profile_exists", return_value=False), \
             patch.object(
                 contractors_route.db_client, "create_contractor_profile",
                 return_value=_profile_row(profile_id, user_id),
             ) as mock_create:
            resp = client.post("/api/contractors/profile", json={"business_name": "Acme Roofing"})

        assert resp.status_code == 201
        assert resp.json()["business_name"] == "Acme Roofing"
        mock_create.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_create_profile_conflict_when_already_exists() -> None:
    user_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(contractors_route.db_client, "contractor_profile_exists", return_value=True), \
             patch.object(contractors_route.db_client, "create_contractor_profile") as mock_create:
            resp = client.post("/api/contractors/profile", json={"business_name": "Acme Roofing"})

        assert resp.status_code == 409
        mock_create.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_get_profile_not_found() -> None:
    user_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(contractors_route.db_client, "get_contractor_profile_by_user", return_value=None):
            resp = client.get("/api/contractors/profile")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_update_profile_passes_only_changed_fields() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            contractors_route.db_client, "update_contractor_profile",
            return_value=_profile_row(profile_id, user_id, business_name="New Name"),
        ) as mock_update:
            resp = client.patch("/api/contractors/profile", json={"business_name": "New Name"})

        assert resp.status_code == 200
        args, kwargs = mock_update.call_args
        assert args[0] == user_id
        assert kwargs == {"business_name": "New Name"}
    finally:
        app.dependency_overrides.clear()


# ── licenses ──────────────────────────────────────────────────────


def test_create_license_success() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            contractors_route.db_client, "create_contractor_license",
            return_value=_license_row(license_id, profile_id),
        ) as mock_create:
            resp = client.post(
                "/api/contractors/licenses",
                json={"trade": "Roofing", "license_number": "TX12345", "expiration_date": "2028-01-01"},
            )

        assert resp.status_code == 201
        assert resp.json()["license_number"] == "TX12345"
        _, kwargs = mock_create.call_args
        assert kwargs["contractor_profile_id"] == profile_id
        assert kwargs["license_number"] == "TX12345"
    finally:
        app.dependency_overrides.clear()


def test_create_license_rejects_invalid_format() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(contractors_route.db_client, "create_contractor_license") as mock_create:
            resp = client.post(
                "/api/contractors/licenses",
                json={"trade": "Roofing", "license_number": "AB-1", "expiration_date": "2028-01-01"},
            )

        assert resp.status_code == 422
        mock_create.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_list_licenses_scoped_to_own_profile() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    rows = [_license_row(uuid4(), profile_id), _license_row(uuid4(), profile_id)]
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(contractors_route.db_client, "list_contractor_licenses", return_value=rows) as mock_list:
            resp = client.get("/api/contractors/licenses")

        assert resp.status_code == 200
        assert len(resp.json()) == 2
        mock_list.assert_called_once_with(profile_id)
    finally:
        app.dependency_overrides.clear()


def test_update_license_404_when_owned_by_different_contractor() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    other_profile_id = uuid4()
    license_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            contractors_route.db_client, "get_contractor_license",
            return_value=_license_row(license_id, other_profile_id),
        ), patch.object(contractors_route.db_client, "update_contractor_license") as mock_update:
            resp = client.patch(f"/api/contractors/licenses/{license_id}", json={"trade": "Electrical"})

        assert resp.status_code == 404
        mock_update.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_delete_license_success_when_own() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            contractors_route.db_client, "get_contractor_license",
            return_value=_license_row(license_id, profile_id),
        ), patch.object(contractors_route.db_client, "delete_contractor_license", return_value=True) as mock_delete:
            resp = client.delete(f"/api/contractors/licenses/{license_id}")

        assert resp.status_code == 200
        mock_delete.assert_called_once_with(license_id)
    finally:
        app.dependency_overrides.clear()


# ── auth gate ─────────────────────────────────────────────────────


def test_require_contractor_profile_403_without_profile() -> None:
    user_id = uuid4()
    app.dependency_overrides[contractors_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(contractors_route.db_client, "get_contractor_profile_by_user", return_value=None):
            resp = client.get("/api/contractors/licenses")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
