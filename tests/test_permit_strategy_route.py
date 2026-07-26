"""
tests/test_permit_strategy_route.py — GET /projects/{id}/permit-strategy (#11)
=============================================================================
The Permit Strategy agent surfaced on a project. Deterministic (use_llm=False):
permit set + pull order + fee estimate, from the project's stored work types.
Membership-gated; fully mocked.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from api.routes import projects as projects_route


def _auth(role: str):
    app.dependency_overrides[projects_route.get_current_user] = lambda: {
        "user_id": uuid4(), "role": "member", "username": "tester",
    }
    return patch.object(projects_route.db_client, "get_project_role", return_value=role)


def test_permit_strategy_for_project(monkeypatch) -> None:
    """A project with real work types returns permits, sequence, and fees."""
    project = {"id": uuid4(), "work_types": ["Structural / Framing", "Electrical"],
               "municipality": "plano"}
    with _auth("viewer"), patch.object(projects_route.db_client, "get_project", return_value=project):
        try:
            r = TestClient(app).get(f"/api/projects/{project['id']}/permit-strategy")
            assert r.status_code == 200
            body = r.json()
            assert body["permits"] == ["Building", "Electrical"]
            # Building is pulled before the electrical rough-in.
            assert body["sequence"].index("Building") < body["sequence"].index("Electrical")
            assert body["estimated_fees_usd"] == 225  # 150 + 75
            assert "plano" in body["notes"].lower()
            assert "estimate" in body["fee_disclaimer"].lower()
        finally:
            app.dependency_overrides.clear()


def test_permit_strategy_cosmetic_only(monkeypatch) -> None:
    """Cosmetic-only work needs no permits."""
    project = {"id": uuid4(), "work_types": ["Flooring"], "municipality": "dallas"}
    with _auth("owner"), patch.object(projects_route.db_client, "get_project", return_value=project):
        try:
            r = TestClient(app).get(f"/api/projects/{project['id']}/permit-strategy")
            assert r.status_code == 200
            assert r.json()["permits"] == []
        finally:
            app.dependency_overrides.clear()


def test_permit_strategy_404_for_missing_project() -> None:
    """A missing project is a 404."""
    with _auth("viewer"), patch.object(projects_route.db_client, "get_project", return_value=None):
        try:
            r = TestClient(app).get(f"/api/projects/{uuid4()}/permit-strategy")
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()


def test_permit_strategy_403_for_non_member() -> None:
    """A non-member (no role) is forbidden."""
    with _auth(None):
        try:
            r = TestClient(app).get(f"/api/projects/{uuid4()}/permit-strategy")
            assert r.status_code == 403
        finally:
            app.dependency_overrides.clear()
