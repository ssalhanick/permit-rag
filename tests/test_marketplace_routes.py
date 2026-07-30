"""
tests/test_marketplace_routes.py — marketplace browse/detail + the
project-side open/close-bidding toggle. Same TestClient + dependency_overrides
+ patch.object(db_client, ...) pattern as the other route test files.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.contractor_auth import require_contractor_profile
from api.main import app
from api.routes import marketplace as marketplace_route
from api.routes import projects as projects_route

client = TestClient(app)


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


def _profile_row(profile_id, user_id):
    return {"id": profile_id, "user_id": user_id, "business_name": "Acme Roofing"}


def _project_row(project_id, owner_id, **overrides):
    now = datetime.now(UTC)
    row = {
        "id": project_id,
        "name": "Kitchen Remodel",
        "owner_user_id": owner_id,
        "is_archived": False,
        "created_at": now,
        "updated_at": now,
        "municipality": "dallas",
        "address": "123 Main St",
        "work_types": ["Roofing"],
        "marketplace_status": "unlisted",
        "listed_at": None,
        "bidding_closes_at": None,
        "awarded_bid_id": None,
    }
    row.update(overrides)
    return row


# ── browse / detail ───────────────────────────────────────────────


def test_browse_projects_passes_filters_through() -> None:
    contractor_id = uuid4()
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(uuid4(), contractor_id)
    try:
        with patch.object(marketplace_route.db_client, "list_marketplace_projects", return_value=[]) as mock_list:
            resp = client.get("/api/marketplace/projects?trade=Roofing&municipality=dallas")

        assert resp.status_code == 200
        mock_list.assert_called_once_with(trade="Roofing", municipality="dallas")
    finally:
        app.dependency_overrides.clear()


def test_browse_projects_requires_contractor_profile() -> None:
    """Leaves require_contractor_profile un-overridden so the real 403 gate runs;
    only its DB lookup is mocked, to a "no profile" result."""
    from api.auth import get_current_user as real_get_current_user

    user_id = uuid4()
    app.dependency_overrides[real_get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(marketplace_route.db_client, "get_contractor_profile_by_user", return_value=None):
            resp = client.get("/api/marketplace/projects")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_listing_detail_404_when_not_open() -> None:
    project_id = uuid4()
    contractor_id = uuid4()
    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(uuid4(), contractor_id)
    try:
        with patch.object(
            marketplace_route.db_client, "get_project",
            return_value=_project_row(project_id, uuid4(), marketplace_status="unlisted"),
        ):
            resp = client.get(f"/api/marketplace/projects/{project_id}")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_listing_detail_returns_room_scan_and_materials_estimate() -> None:
    project_id = uuid4()
    contractor_id = uuid4()
    project = _project_row(project_id, uuid4(), marketplace_status="open")
    scan_row = {"scan_type": "room", "is_active": True, "derived": {"floor_area_sqm": 12.5}}
    estimate = {"lines": [], "total_low": None, "total_high": None, "disclaimer": "Estimate only"}

    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(uuid4(), contractor_id)
    try:
        with patch.object(marketplace_route.db_client, "get_project", return_value=project), \
             patch.object(
                 marketplace_route.db_client, "list_linked_project_room_scans", return_value=[scan_row],
             ), \
             patch.object(
                 marketplace_route, "build_project_materials_estimate", return_value=estimate,
             ):
            resp = client.get(f"/api/marketplace/projects/{project_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["project"]["id"] == str(project_id)
        assert body["room_scan_summary"] == {"floor_area_sqm": 12.5}
        assert body["materials_estimate"]["disclaimer"] == "Estimate only"
    finally:
        app.dependency_overrides.clear()


# ── homeowner-side open/close toggle ───────────────────────────────


def test_set_marketplace_status_owner_can_open() -> None:
    owner_id = uuid4()
    project_id = uuid4()
    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 projects_route.db_client, "set_project_marketplace_status",
                 return_value=_project_row(project_id, owner_id, marketplace_status="open"),
             ) as mock_set:
            resp = client.patch(
                f"/api/projects/{project_id}/marketplace-status",
                json={"marketplace_status": "open"},
            )

        assert resp.status_code == 200
        assert resp.json()["marketplace_status"] == "open"
        mock_set.assert_called_once_with(project_id, "open")
    finally:
        app.dependency_overrides.clear()


def test_set_marketplace_status_rejects_direct_award() -> None:
    owner_id = uuid4()
    project_id = uuid4()
    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(projects_route.db_client, "set_project_marketplace_status") as mock_set:
            resp = client.patch(
                f"/api/projects/{project_id}/marketplace-status",
                json={"marketplace_status": "awarded"},
            )

        assert resp.status_code == 422
        mock_set.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_set_marketplace_status_non_owner_forbidden() -> None:
    editor_id = uuid4()
    project_id = uuid4()
    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(editor_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="editor"):
            resp = client.patch(
                f"/api/projects/{project_id}/marketplace-status",
                json={"marketplace_status": "open"},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
