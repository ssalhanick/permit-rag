"""
tests/test_overlays_routes.py — overlay petition/approve/reject routes.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.routes import overlays as overlays_route
from api.routes.upload import UPLOAD_DIR

client = TestClient(app)


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


def _overlay_row(overlay_id, project_id, **overrides):
    row = {
        "id": overlay_id,
        "name": "Swiss Avenue Historic District",
        "overlay_type": "historic_district",
        "jurisdiction_id": "dallas",
        "status": "petitioned",
        "petitioning_project_id": project_id,
        "approved_by": None,
        "approved_at": None,
        "notes": None,
        "created_at": datetime.now(UTC),
    }
    row.update(overrides)
    return row


def test_petition_overlay_requires_editor_or_owner_role() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[overlays_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            overlays_route, "_require_role",
            side_effect=HTTPException(status_code=403, detail="Insufficient project privileges."),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/overlays",
                files={"file": ("bylaws.pdf", b"fake", "application/pdf")},
                data={"name": "Oak Hollow HOA", "overlay_type": "hoa"},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_petition_overlay_rejects_invalid_overlay_type() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[overlays_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(overlays_route, "_require_role", return_value=None):
            resp = client.post(
                f"/api/projects/{project_id}/overlays",
                files={"file": ("bylaws.pdf", b"fake", "application/pdf")},
                data={"name": "Oak Hollow HOA", "overlay_type": "not_a_real_type"},
            )
        assert resp.status_code == 400
        assert "overlay_type" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_petition_overlay_requires_project_coordinates() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[overlays_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(overlays_route, "_require_role", return_value=None), \
             patch.object(
                 overlays_route.db_client, "get_project",
                 return_value={"id": project_id, "municipality": "dallas", "latitude": None, "longitude": None},
             ):
            resp = client.post(
                f"/api/projects/{project_id}/overlays",
                files={"file": ("bylaws.pdf", b"fake", "application/pdf")},
                data={"name": "Oak Hollow HOA", "overlay_type": "hoa"},
            )
        assert resp.status_code == 400
        assert "address" in resp.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_petition_overlay_success_schedules_background_processing() -> None:
    project_id = uuid4()
    user_id = uuid4()
    overlay_id = uuid4()

    app.dependency_overrides[overlays_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(overlays_route, "_require_role", return_value=None), \
             patch.object(
                 overlays_route.db_client, "get_project",
                 return_value={
                     "id": project_id, "municipality": "dallas",
                     "latitude": 32.8, "longitude": -96.78,
                 },
             ), \
             patch.object(
                 overlays_route.db_client, "create_overlay_petition",
                 return_value=_overlay_row(overlay_id, project_id),
             ) as mock_create, \
             patch.object(overlays_route, "_process_upload") as mock_process:
            resp = client.post(
                f"/api/projects/{project_id}/overlays",
                files={"file": ("swiss_ave.pdf", b"fake pdf bytes", "application/pdf")},
                data={"name": "Swiss Avenue Historic District", "overlay_type": "historic_district"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == str(overlay_id)
        assert body["status"] == "petitioned"

        mock_create.assert_called_once()
        _, create_kwargs = mock_create.call_args
        assert create_kwargs["overlay_type"] == "historic_district"
        assert create_kwargs["petitioning_project_id"] == project_id
        assert create_kwargs["latitude"] == 32.8

        mock_process.assert_called_once()
        _, process_kwargs = mock_process.call_args
        assert process_kwargs["overlay_id"] == overlay_id
        assert process_kwargs["project_id"] == project_id
        assert process_kwargs["source_tier"] == 3
        assert process_kwargs["doc_type"] == "zoning_ordinance"
        # An unapproved overlay's document must stay out of match_chunks
        # (which has no source_tier exclusion) until the overlay itself is
        # approved -- see approve_overlay's document-activation UPDATE.
        assert process_kwargs["auto_activate"] is False
    finally:
        app.dependency_overrides.clear()
        with contextlib.suppress(FileNotFoundError):
            (UPLOAD_DIR / f"overlay-{overlay_id}.pdf").unlink()


def test_petition_overlay_rejects_when_rate_limited() -> None:
    """Rate limit must be enforced before create_overlay_petition -- a failed
    check must not strand an orphaned overlay row with no document."""
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[overlays_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(overlays_route, "_require_role", return_value=None), \
             patch.object(
                 overlays_route.db_client, "get_project",
                 return_value={"id": project_id, "municipality": "dallas", "latitude": 32.8, "longitude": -96.78},
             ), \
             patch.object(overlays_route.db_client, "count_recent_documents_by_user", return_value=10), \
             patch.object(overlays_route.db_client, "create_overlay_petition") as mock_create:
            resp = client.post(
                f"/api/projects/{project_id}/overlays",
                files={"file": ("bylaws.pdf", b"fake", "application/pdf")},
                data={"name": "Oak Hollow HOA", "overlay_type": "hoa"},
            )
        assert resp.status_code == 429
        mock_create.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_petition_overlay_rejects_duplicate_checksum_before_creating_row() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[overlays_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(overlays_route, "_require_role", return_value=None), \
             patch.object(
                 overlays_route.db_client, "get_project",
                 return_value={"id": project_id, "municipality": "dallas", "latitude": 32.8, "longitude": -96.78},
             ), \
             patch.object(overlays_route.db_client, "count_recent_documents_by_user", return_value=0), \
             patch.object(
                 overlays_route.db_client, "get_document_by_checksum",
                 return_value={"doc_id": "overlay-existing", "document_status": "draft"},
             ), \
             patch.object(overlays_route.db_client, "create_overlay_petition") as mock_create:
            resp = client.post(
                f"/api/projects/{project_id}/overlays",
                files={"file": ("bylaws.pdf", b"identical bytes", "application/pdf")},
                data={"name": "Oak Hollow HOA", "overlay_type": "hoa"},
            )
        assert resp.status_code == 409
        mock_create.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_list_pending_overlays_requires_admin_auth() -> None:
    with patch.object(
        overlays_route, "_require_admin_auth",
        side_effect=HTTPException(status_code=401, detail="Authentication required."),
    ):
        resp = client.get("/api/admin/overlays/pending")
    assert resp.status_code == 401


def test_list_pending_overlays_returns_rows() -> None:
    overlay_id = uuid4()
    project_id = uuid4()
    with patch.object(overlays_route, "_require_admin_auth", return_value=None), \
         patch.object(
             overlays_route.db_client, "list_pending_overlay_petitions",
             return_value=[_overlay_row(overlay_id, project_id)],
         ):
        resp = client.get("/api/admin/overlays/pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_approve_overlay_route() -> None:
    overlay_id = uuid4()
    project_id = uuid4()
    approver_id = uuid4()
    with patch.object(overlays_route, "_require_admin_auth", return_value=None), \
         patch.object(
             overlays_route.db_client, "approve_overlay",
             return_value=_overlay_row(overlay_id, project_id, status="approved", approved_by=approver_id),
         ) as mock_approve:
        resp = client.patch(
            f"/api/admin/overlays/{overlay_id}/approve",
            json={"geojson_polygon": None},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    mock_approve.assert_called_once_with(overlay_id, approved_by=None, geojson_polygon=None)


def test_reject_overlay_route() -> None:
    overlay_id = uuid4()
    project_id = uuid4()
    with patch.object(overlays_route, "_require_admin_auth", return_value=None), \
         patch.object(
             overlays_route.db_client, "reject_overlay",
             return_value=_overlay_row(overlay_id, project_id, status="rejected"),
         ):
        resp = client.post(f"/api/admin/overlays/{overlay_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_approve_overlay_route_404_when_missing() -> None:
    overlay_id = uuid4()
    with patch.object(overlays_route, "_require_admin_auth", return_value=None), \
         patch.object(overlays_route.db_client, "approve_overlay", return_value=None):
        resp = client.patch(
            f"/api/admin/overlays/{overlay_id}/approve",
            json={},
        )
    assert resp.status_code == 404
