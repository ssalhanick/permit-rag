"""
tests/test_document_petitions.py — Type 1 jurisdiction ordinance petitions:
tiered-trust auto-approval, admin pending/approve/reject, and the
_process_upload auto_activate gate that makes the pending queue actually
stay pending (match_chunks has no source_tier filter, so 'active' alone is
what keeps a tier-2 draft out of the shared corpus).
"""

from __future__ import annotations

import contextlib
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.main import app
from api.routes import document_petitions as petitions_route
from api.routes.upload import UPLOAD_DIR
from db import client as db_client

client = TestClient(app)


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


def _cleanup_upload_dir_prefix(prefix: str) -> None:
    for f in UPLOAD_DIR.glob(f"{prefix}*"):
        with contextlib.suppress(FileNotFoundError):
            f.unlink()


def _document_row(doc_id, **overrides):
    row = {
        "id": uuid4(),
        "doc_id": doc_id,
        "source_url": f"file:///documents/raw/{doc_id}.pdf",
        "municipality": "dallas",
        "authority_level": "municipal",
        "doc_type": "zoning_ordinance",
        "subject_tags": [],
        "document_status": "draft",
        "is_current": True,
        "effective_date": None,
        "review_due": None,
        "retrieval_weight": 1.0,
        "updated_at": "2026-07-30T00:00:00Z",
    }
    row.update(overrides)
    return row


# ── POST /documents/petitions ──────────────────────────────────


def test_petition_rejects_invalid_extension() -> None:
    user_id = uuid4()
    app.dependency_overrides[petitions_route.get_current_user] = lambda: _current_user(user_id)
    try:
        resp = client.post(
            "/api/documents/petitions",
            files={"file": ("ordinance.exe", b"fake", "application/octet-stream")},
            data={"municipality": "dallas", "authority_level": "municipal", "doc_type": "zoning_ordinance"},
        )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_petition_rejects_invalid_authority_level() -> None:
    user_id = uuid4()
    app.dependency_overrides[petitions_route.get_current_user] = lambda: _current_user(user_id)
    try:
        resp = client.post(
            "/api/documents/petitions",
            files={"file": ("ordinance.pdf", b"fake", "application/pdf")},
            data={"municipality": "dallas", "authority_level": "planet", "doc_type": "zoning_ordinance"},
        )
        assert resp.status_code == 400
        assert "authority_level" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_petition_rejects_invalid_doc_type() -> None:
    user_id = uuid4()
    app.dependency_overrides[petitions_route.get_current_user] = lambda: _current_user(user_id)
    try:
        resp = client.post(
            "/api/documents/petitions",
            files={"file": ("ordinance.pdf", b"fake", "application/pdf")},
            data={"municipality": "dallas", "authority_level": "municipal", "doc_type": "not_a_real_type"},
        )
        assert resp.status_code == 400
        assert "doc_type" in resp.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_petition_from_regular_member_lands_in_pending_queue() -> None:
    """No is_verified_contributor -> tier 2, auto_activate=False."""
    user_id = uuid4()
    app.dependency_overrides[petitions_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            petitions_route.db_client, "get_user_by_id",
            return_value={"id": user_id, "is_verified_contributor": False},
        ), patch.object(petitions_route, "_process_upload") as mock_process:
            resp = client.post(
                "/api/documents/petitions",
                files={"file": ("plano_ordinance.pdf", b"fake pdf", "application/pdf")},
                data={"municipality": "Plano", "authority_level": "municipal", "doc_type": "zoning_ordinance"},
            )

        assert resp.status_code == 201
        assert "queued for staff review" in resp.json()["message"]

        mock_process.assert_called_once()
        _, kwargs = mock_process.call_args
        assert kwargs["source_tier"] == 2
        assert kwargs["auto_activate"] is False
        assert kwargs["municipality"] == "plano"  # canonicalized
        assert kwargs["uploaded_by"] == user_id
    finally:
        app.dependency_overrides.clear()
        _cleanup_upload_dir_prefix("ordinance-petition-")


def test_petition_from_verified_contributor_auto_approves() -> None:
    """is_verified_contributor=True -> tier 1, auto_activate=True, straight to active."""
    user_id = uuid4()
    app.dependency_overrides[petitions_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            petitions_route.db_client, "get_user_by_id",
            return_value={"id": user_id, "is_verified_contributor": True},
        ), patch.object(petitions_route, "_process_upload") as mock_process:
            resp = client.post(
                "/api/documents/petitions",
                files={"file": ("dallas_code.pdf", b"fake pdf", "application/pdf")},
                data={"municipality": "dallas", "authority_level": "municipal", "doc_type": "building_code"},
            )

        assert resp.status_code == 201
        assert "auto-approved" in resp.json()["message"]

        _, kwargs = mock_process.call_args
        assert kwargs["source_tier"] == 1
        assert kwargs["auto_activate"] is True
    finally:
        app.dependency_overrides.clear()
        _cleanup_upload_dir_prefix("ordinance-petition-")


def test_petition_treats_missing_user_row_as_unverified() -> None:
    """get_user_by_id returning None (e.g. inactive) must not crash and must
    default to the safer (pending-queue) path."""
    user_id = uuid4()
    app.dependency_overrides[petitions_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(petitions_route.db_client, "get_user_by_id", return_value=None), \
             patch.object(petitions_route, "_process_upload") as mock_process:
            resp = client.post(
                "/api/documents/petitions",
                files={"file": ("ordinance.pdf", b"fake pdf", "application/pdf")},
                data={"municipality": "dallas", "authority_level": "municipal", "doc_type": "zoning_ordinance"},
            )
        assert resp.status_code == 201
        _, kwargs = mock_process.call_args
        assert kwargs["source_tier"] == 2
        assert kwargs["auto_activate"] is False
    finally:
        app.dependency_overrides.clear()
        _cleanup_upload_dir_prefix("ordinance-petition-")


# ── GET/PATCH/POST /admin/documents/pending|approve|reject ────


def test_list_pending_documents_requires_admin_auth() -> None:
    with patch.object(
        petitions_route, "_require_admin_auth",
        side_effect=HTTPException(status_code=401, detail="Authentication required."),
    ):
        resp = client.get("/api/admin/documents/pending")
    assert resp.status_code == 401


def test_list_pending_documents_returns_rows() -> None:
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(
             petitions_route.db_client, "get_pending_documents",
             return_value=[_document_row("ordinance-petition-abc")],
         ):
        resp = client.get("/api/admin/documents/pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["doc_id"] == "ordinance-petition-abc"


def test_approve_document_route() -> None:
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(
             petitions_route.db_client, "approve_pending_document",
             return_value=_document_row("ordinance-petition-abc", document_status="active"),
         ) as mock_approve:
        resp = client.patch("/api/admin/documents/ordinance-petition-abc/approve")
    assert resp.status_code == 200
    assert resp.json()["document_status"] == "active"
    mock_approve.assert_called_once_with("ordinance-petition-abc")


def test_approve_document_route_404_when_missing() -> None:
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(petitions_route.db_client, "approve_pending_document", return_value=None):
        resp = client.patch("/api/admin/documents/does-not-exist/approve")
    assert resp.status_code == 404


def test_reject_document_route() -> None:
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(petitions_route.db_client, "reject_pending_document", return_value=True):
        resp = client.post("/api/admin/documents/ordinance-petition-abc/reject")
    assert resp.status_code == 200


def test_reject_document_route_404_when_missing() -> None:
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(petitions_route.db_client, "reject_pending_document", return_value=False):
        resp = client.post("/api/admin/documents/does-not-exist/reject")
    assert resp.status_code == 404


# ── PATCH /admin/users/{user_id}/verified-contributor ──────────


def test_set_verified_contributor_requires_admin_auth() -> None:
    user_id = uuid4()
    with patch.object(
        petitions_route, "_require_admin_auth",
        side_effect=HTTPException(status_code=401, detail="Authentication required."),
    ):
        resp = client.patch(
            f"/api/admin/users/{user_id}/verified-contributor",
            json={"is_verified_contributor": True},
        )
    assert resp.status_code == 401


def test_set_verified_contributor_does_not_leak_password_hash() -> None:
    """The route must never pass the raw users row straight through."""
    user_id = uuid4()
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(
             petitions_route.db_client, "set_user_verified_contributor",
             return_value={
                 "id": user_id, "username": "scott", "is_verified_contributor": True,
                 "password_hash": "argon2id$super-secret-hash",
                 "refresh_token_hash": "some-other-secret",
             },
         ):
        resp = client.patch(
            f"/api/admin/users/{user_id}/verified-contributor",
            json={"is_verified_contributor": True},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"id": str(user_id), "username": "scott", "is_verified_contributor": True}
    assert "password_hash" not in body
    assert "refresh_token_hash" not in body


def test_set_verified_contributor_404_when_user_missing() -> None:
    user_id = uuid4()
    with patch.object(petitions_route, "_require_admin_auth", return_value=None), \
         patch.object(petitions_route.db_client, "set_user_verified_contributor", return_value=None):
        resp = client.patch(
            f"/api/admin/users/{user_id}/verified-contributor",
            json={"is_verified_contributor": True},
        )
    assert resp.status_code == 404


# ── db.client pending-document lifecycle (migration 041) ───────


def _fake_conn(*, fetchone_result=None, fetchall_result=None):
    captured: dict = {"sql": [], "params": []}

    class _FakeResult:
        def __init__(self, rowcount=1):
            self.rowcount = rowcount

        def fetchone(self):
            return fetchone_result

        def fetchall(self):
            return fetchall_result or []

    class _FakeConn:
        def execute(self, sql, params=None):
            captured["sql"].append(sql)
            captured["params"].append(params)
            return _FakeResult()

        def commit(self):
            captured["committed"] = True

    @contextmanager
    def _factory():
        yield _FakeConn()

    return _factory, captured


def test_get_pending_documents_filters_tier2_draft(monkeypatch) -> None:
    factory, captured = _fake_conn(fetchall_result=[{"doc_id": "x", "source_tier": 2}])
    monkeypatch.setattr(db_client, "get_conn", factory)

    rows = db_client.get_pending_documents()

    assert len(rows) == 1
    assert "source_tier = 2" in captured["sql"][0]
    assert "document_status = 'draft'" in captured["sql"][0]


def test_approve_pending_document_scoped_to_tier2(monkeypatch) -> None:
    factory, captured = _fake_conn(fetchone_result={"doc_id": "x", "source_tier": 1, "document_status": "active"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.approve_pending_document("x")

    assert row["source_tier"] == 1
    assert "source_tier = 1" in captured["sql"][0]
    assert "WHERE doc_id = %s AND source_tier = 2" in captured["sql"][0]


def test_reject_pending_document_deletes_chunks_then_document(monkeypatch) -> None:
    document_id = uuid4()
    calls: list[str] = []

    class _FakeConn:
        def execute(self, sql, params=None):
            if sql.strip().startswith("SELECT id FROM documents"):
                calls.append("lookup")
                return type("R", (), {"fetchone": lambda self: {"id": document_id}})()
            if sql.strip().startswith("DELETE FROM chunks"):
                calls.append("chunks")
                return type("R", (), {"rowcount": 3})()
            calls.append("documents")
            return type("R", (), {"rowcount": 1})()

        def commit(self):
            calls.append("commit")

    @contextmanager
    def _factory():
        yield _FakeConn()

    monkeypatch.setattr(db_client, "get_conn", _factory)

    assert db_client.reject_pending_document("x") is True
    assert calls == ["lookup", "chunks", "documents", "commit"]


def test_reject_pending_document_returns_false_when_not_found(monkeypatch) -> None:
    class _FakeConn:
        def execute(self, sql, params=None):
            return type("R", (), {"fetchone": lambda self: None})()

        def commit(self):
            pass

    @contextmanager
    def _factory():
        yield _FakeConn()

    monkeypatch.setattr(db_client, "get_conn", _factory)

    assert db_client.reject_pending_document("does-not-exist") is False


def test_set_user_verified_contributor_scoped_to_active_users(monkeypatch) -> None:
    factory, captured = _fake_conn(fetchone_result={"id": uuid4(), "is_verified_contributor": True})
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.set_user_verified_contributor(uuid4(), True)

    assert "is_active = true" in captured["sql"][0]
    assert captured["params"][0]["value"] is True
