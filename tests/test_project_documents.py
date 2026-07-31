"""
tests/test_project_documents.py — Type 2 project-document upload/delete routes,
plus the tier-3 visibility filter in db.client.match_project_chunks.
"""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.routes import project_documents as pd_route
from api.routes.upload import UPLOAD_DIR
from db import client as db_client

client = TestClient(app)


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


def _cleanup_upload_dir_prefix(prefix: str) -> None:
    for f in UPLOAD_DIR.glob(f"{prefix}*"):
        with contextlib.suppress(FileNotFoundError):
            f.unlink()


# ── POST /projects/{project_id}/documents/upload ──────────────


def test_upload_requires_editor_or_owner_role() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            pd_route, "_require_role",
            side_effect=HTTPException(status_code=403, detail="Insufficient project privileges."),
        ):
            resp = client.post(
                f"/api/projects/{project_id}/documents/upload",
                files={"file": ("plan.pdf", b"fake", "application/pdf")},
            )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_unsupported_extension() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None):
            resp = client.post(
                f"/api/projects/{project_id}/documents/upload",
                files={"file": ("virus.exe", b"fake", "application/octet-stream")},
            )
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_upload_404_when_project_missing() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None), \
             patch.object(pd_route.db_client, "get_project", return_value=None):
            resp = client.post(
                f"/api/projects/{project_id}/documents/upload",
                files={"file": ("plan.pdf", b"fake", "application/pdf")},
            )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_upload_chunkable_file_schedules_background_processing() -> None:
    project_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None), \
             patch.object(
                 pd_route.db_client, "get_project",
                 return_value={"id": project_id, "municipality": "dallas"},
             ), \
             patch.object(pd_route, "_process_upload") as mock_process, \
             patch.object(pd_route.db_client, "insert_document") as mock_insert, \
             patch.object(pd_route.db_client, "share_document_to_project") as mock_share:
            resp = client.post(
                f"/api/projects/{project_id}/documents/upload",
                files={"file": ("floorplan.pdf", b"fake pdf bytes", "application/pdf")},
                data={"visibility": "private"},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "processing"

        mock_process.assert_called_once()
        _, kwargs = mock_process.call_args
        assert kwargs["source_tier"] == 3
        assert kwargs["project_id"] == project_id
        assert kwargs["uploaded_by"] == user_id
        assert kwargs["visibility"] == "private"
        assert kwargs["doc_type"] == "other"

        # Chunkable path defers document creation to the background task.
        mock_insert.assert_not_called()
        mock_share.assert_not_called()
    finally:
        app.dependency_overrides.clear()
        _cleanup_upload_dir_prefix("project-doc-")


def test_upload_artifact_only_file_skips_background_processing() -> None:
    project_id = uuid4()
    user_id = uuid4()
    document_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None), \
             patch.object(
                 pd_route.db_client, "get_project",
                 return_value={"id": project_id, "municipality": "dallas"},
             ), \
             patch.object(pd_route, "_process_upload") as mock_process, \
             patch.object(
                 pd_route.db_client, "insert_document",
                 return_value={"id": document_id},
             ) as mock_insert, \
             patch.object(pd_route.db_client, "share_document_to_project") as mock_share:
            resp = client.post(
                f"/api/projects/{project_id}/documents/upload",
                files={"file": ("site_plan.dwg", b"fake cad bytes", "application/octet-stream")},
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "active"

        mock_process.assert_not_called()
        mock_insert.assert_called_once()
        _, insert_kwargs = mock_insert.call_args
        assert insert_kwargs["source_tier"] == 3
        assert insert_kwargs["document_status"] == "active"
        assert insert_kwargs["visibility"] == "team"  # default when omitted

        mock_share.assert_called_once_with(project_id, document_id, user_id)
    finally:
        app.dependency_overrides.clear()
        _cleanup_upload_dir_prefix("project-doc-")


# ── DELETE /projects/{project_id}/documents/upload/{document_id} ──


def test_delete_requires_editor_or_owner_role() -> None:
    project_id = uuid4()
    document_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            pd_route, "_require_role",
            side_effect=HTTPException(status_code=403, detail="Insufficient project privileges."),
        ):
            resp = client.delete(f"/api/projects/{project_id}/documents/upload/{document_id}")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_delete_404_when_document_belongs_to_different_project() -> None:
    project_id = uuid4()
    other_project_id = uuid4()
    document_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None), \
             patch.object(
                 pd_route.db_client, "get_document_by_uuid",
                 return_value={"id": document_id, "source_tier": 3, "project_id": other_project_id},
             ):
            resp = client.delete(f"/api/projects/{project_id}/documents/upload/{document_id}")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_404_when_document_is_not_tier_3() -> None:
    project_id = uuid4()
    document_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None), \
             patch.object(
                 pd_route.db_client, "get_document_by_uuid",
                 return_value={"id": document_id, "source_tier": 1, "project_id": project_id},
             ):
            resp = client.delete(f"/api/projects/{project_id}/documents/upload/{document_id}")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_delete_success_calls_cascade_delete() -> None:
    project_id = uuid4()
    document_id = uuid4()
    user_id = uuid4()

    app.dependency_overrides[pd_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(pd_route, "_require_role", return_value=None), \
             patch.object(
                 pd_route.db_client, "get_document_by_uuid",
                 return_value={"id": document_id, "source_tier": 3, "project_id": project_id},
             ), \
             patch.object(
                 pd_route.db_client, "delete_project_document", return_value=True,
             ) as mock_delete:
            resp = client.delete(f"/api/projects/{project_id}/documents/upload/{document_id}")
        assert resp.status_code == 200
        mock_delete.assert_called_once_with(document_id)
    finally:
        app.dependency_overrides.clear()


# ── db.client.match_project_chunks visibility filter (migration 040) ──


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


def test_match_project_chunks_sql_gates_tier3_on_visibility(monkeypatch) -> None:
    """Tier-2 rows are unconditional; tier-3 rows require team visibility or ownership."""
    factory, captured = _fake_conn()
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.match_project_chunks([0.1, 0.2], project_id=uuid4())

    assert "d.source_tier = 2" in captured["sql"]
    assert "d.visibility = 'team'" in captured["sql"]
    assert "d.uploaded_by = %(requesting_user_id)s" in captured["sql"]


def test_match_project_chunks_passes_requesting_user_id(monkeypatch) -> None:
    factory, captured = _fake_conn()
    monkeypatch.setattr(db_client, "get_conn", factory)
    user_id = uuid4()

    db_client.match_project_chunks([0.1, 0.2], project_id=uuid4(), requesting_user_id=user_id)

    assert captured["params"]["requesting_user_id"] == user_id


def test_match_project_chunks_defaults_requesting_user_id_to_none(monkeypatch) -> None:
    """No requesting user (e.g. unauthenticated) must not crash -- private docs
    simply never match a NULL uploaded_by comparison."""
    factory, captured = _fake_conn()
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.match_project_chunks([0.1, 0.2], project_id=uuid4())

    assert captured["params"]["requesting_user_id"] is None


# ── db.client.delete_project_document (migration 040 cascade-delete) ──


def test_delete_project_document_deletes_chunks_then_document(monkeypatch) -> None:
    document_id = uuid4()
    calls: list[str] = []

    class _FakeCursor:
        def __init__(self, rowcount):
            self.rowcount = rowcount

    class _FakeConn:
        def execute(self, sql, params=None):
            if sql.strip().startswith("DELETE FROM chunks"):
                calls.append("chunks")
                return _FakeCursor(2)
            calls.append("documents")
            return _FakeCursor(1)

        def commit(self):
            calls.append("commit")

    @contextmanager
    def _factory():
        yield _FakeConn()

    monkeypatch.setattr(db_client, "get_conn", _factory)

    result = db_client.delete_project_document(document_id)

    assert result is True
    assert calls == ["chunks", "documents", "commit"]


def test_delete_project_document_returns_false_when_not_found(monkeypatch) -> None:
    class _FakeCursor:
        rowcount = 0

    class _FakeConn:
        def execute(self, sql, params=None):
            return _FakeCursor()

        def commit(self):
            pass

    @contextmanager
    def _factory():
        yield _FakeConn()

    monkeypatch.setattr(db_client, "get_conn", _factory)

    assert db_client.delete_project_document(uuid4()) is False
