"""
tests/test_project_delete_routes.py — superadmin bypass + audit logging for
project soft-delete / restore / hard-delete routes.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from api.routes import projects as projects_route


def _project_row(project_id, owner_id):
    return {
        "id": project_id,
        "name": "Kitchen Remodel",
        "owner_user_id": owner_id,
        "deleted_at": None,
    }


def test_superadmin_can_soft_delete_project_they_do_not_own() -> None:
    """A superadmin (not a project member) should bypass the owner-only role check."""
    project_id = uuid4()
    owner_id = uuid4()
    superadmin_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: {
        "user_id": superadmin_id,
        "role": "superadmin",
        "username": "qa-superadmin",
    }
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value=None), \
             patch.object(
                 projects_route.db_client, "soft_delete_project",
                 return_value=_project_row(project_id, owner_id),
             ) as mock_soft_delete, \
             patch.object(projects_route.db_client, "insert_project_delete_audit_log") as mock_audit:
            client = TestClient(app)
            resp = client.delete(f"/api/projects/{project_id}")

        assert resp.status_code == 200
        mock_soft_delete.assert_called_once_with(project_id)
        mock_audit.assert_called_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["actor_user_id"] == superadmin_id
        assert kwargs["actor_role"] == "superadmin"
        assert kwargs["action"] == "soft_delete"
        assert kwargs["owner_user_id"] == owner_id
    finally:
        app.dependency_overrides.clear()


def test_superadmin_can_hard_delete_project_they_do_not_own() -> None:
    """Hard delete should fetch the project first (for the audit snapshot), then delete + log."""
    project_id = uuid4()
    owner_id = uuid4()
    superadmin_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: {
        "user_id": superadmin_id,
        "role": "superadmin",
        "username": "qa-superadmin",
    }
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value=None), \
             patch.object(
                 projects_route.db_client, "get_project",
                 return_value=_project_row(project_id, owner_id),
             ), \
             patch.object(projects_route.db_client, "hard_delete_project", return_value=True), \
             patch.object(projects_route.db_client, "insert_project_delete_audit_log") as mock_audit:
            client = TestClient(app)
            resp = client.delete(f"/api/projects/{project_id}/permanent")

        assert resp.status_code == 200
        mock_audit.assert_called_once()
        _, kwargs = mock_audit.call_args
        assert kwargs["action"] == "hard_delete"
        assert kwargs["actor_role"] == "superadmin"
    finally:
        app.dependency_overrides.clear()


def test_non_owner_member_cannot_soft_delete_project() -> None:
    """A plain viewer (not owner, not staff) should still be blocked with 403."""
    project_id = uuid4()
    viewer_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: {
        "user_id": viewer_id,
        "role": "member",
        "username": "qa-viewer",
    }
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="viewer"), \
             patch.object(projects_route.db_client, "soft_delete_project") as mock_soft_delete, \
             patch.object(projects_route.db_client, "insert_project_delete_audit_log") as mock_audit:
            client = TestClient(app)
            resp = client.delete(f"/api/projects/{project_id}")

        assert resp.status_code == 403
        mock_soft_delete.assert_not_called()
        mock_audit.assert_not_called()
    finally:
        app.dependency_overrides.clear()
