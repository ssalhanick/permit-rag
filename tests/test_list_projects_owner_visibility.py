"""
tests/test_list_projects_owner_visibility.py — superadmin project-visibility
=============================================================================
list_all_projects() joins the owner's username/email so a superadmin can
disambiguate whose project they're looking at in a blended list; the
member-scoped list_projects_for_user() deliberately does not carry it.
"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from db import client as db_client


def _fake_conn(*, fetchall_result=None):
    captured: dict = {"sql": None, "params": None}

    class _FakeResult:
        def fetchall(self):
            return fetchall_result or []

    class _FakeConn:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return _FakeResult()

    @contextmanager
    def _factory():
        yield _FakeConn()

    return _factory, captured


def test_list_all_projects_sql_joins_owner_username_and_email(monkeypatch) -> None:
    factory, captured = _fake_conn()
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.list_all_projects()

    assert "u.username AS owner_username" in captured["sql"]
    assert "u.email AS owner_email" in captured["sql"]
    assert "LEFT JOIN users u ON u.id = p.owner_user_id" in captured["sql"]


def test_list_projects_route_returns_owner_fields_for_superadmin(monkeypatch) -> None:
    """A superadmin's blended project list carries the owner's identity."""
    from api.routes import projects as projects_route

    owner_id = uuid4()
    project_id = uuid4()
    row = {
        "id": project_id,
        "name": "Someone Else's Garage",
        "description": None,
        "owner_user_id": owner_id,
        "owner_username": "jsmith",
        "owner_email": "jsmith@example.com",
        "municipality": "dallas",
        "is_archived": False,
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    monkeypatch.setattr(projects_route.db_client, "list_all_projects", lambda **_k: [row])
    app.dependency_overrides[projects_route.get_current_user] = lambda: {
        "user_id": uuid4(), "role": "superadmin", "username": "admin",
    }
    try:
        client = TestClient(app)
        resp = client.get("/api/projects/")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["owner_username"] == "jsmith"
        assert body[0]["owner_email"] == "jsmith@example.com"
    finally:
        app.dependency_overrides.clear()


def test_list_projects_route_omits_owner_fields_for_regular_member(monkeypatch) -> None:
    """A regular member's own project list never carries other users' identity —
    list_projects_for_user()'s query doesn't select it in the first place."""
    from api.routes import projects as projects_route

    user_id = uuid4()
    project_id = uuid4()
    row = {
        "id": project_id,
        "name": "My Own Project",
        "description": None,
        "owner_user_id": user_id,
        "municipality": "dallas",
        "is_archived": False,
        "deleted_at": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    monkeypatch.setattr(projects_route.db_client, "list_projects_for_user", lambda *_a, **_k: [row])
    app.dependency_overrides[projects_route.get_current_user] = lambda: {
        "user_id": user_id, "role": "member", "username": "regular-user",
    }
    try:
        client = TestClient(app)
        resp = client.get("/api/projects/")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["owner_username"] is None
        assert body[0]["owner_email"] is None
    finally:
        app.dependency_overrides.clear()
