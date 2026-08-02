"""
tests/test_documents_routes.py — API tests for documents routes
===============================================================
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture(autouse=True)
def _admin_auth_defaults(monkeypatch) -> None:
    """Default tests to admin auth disabled unless explicitly enabled."""
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "false")
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("API_ADMIN_ALLOWED_ROLES", raising=False)


def _override_user(user_id=None, role: str = "member") -> dict:
    """Install a fake authenticated user for GET /documents* routes (migration 045's
    auth-gate — these were previously reachable unauthenticated)."""
    from api.routes import documents as documents_route

    user = {"user_id": user_id or uuid4(), "role": role, "username": "tester"}
    app.dependency_overrides[documents_route.get_current_user] = lambda: user
    return user


@pytest.fixture(autouse=True)
def _default_authenticated_user():
    """Every test in this file gets some authenticated (non-staff) user by
    default; tests needing a specific user_id/role call _override_user again."""
    _override_user()
    yield
    app.dependency_overrides.clear()


def _document_row(doc_id: str = "dallas-building-code") -> dict:
    """Build a realistic documents table row for route tests."""
    return {
        "id": uuid4(),
        "doc_id": doc_id,
        "source_url": "https://example.org/code",
        "municipality": "dallas",
        "authority_level": "municipal",
        "doc_type": "building_code",
        "subject_tags": ["permit", "construction"],
        "effective_date": date(2025, 1, 15),
        "document_status": "active",
        "is_current": True,
        "retrieval_weight": Decimal("1.00"),
        "review_due": date(2026, 1, 15),
        "checksum_sha256": "abc123",
        "source_etag": "etag-1",
        "local_path": "documents/raw/dallas-building-code.pdf",
        "ingested_at": datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc),
        "superseded_by": None,
        "source_tier": 1,
    }


def test_list_documents_applies_all_filters(monkeypatch) -> None:
    """GET /documents (superadmin) should pass municipality/status/authority/doc_type
    filters through to the full-corpus query."""
    from api.routes import documents as documents_route

    _override_user(role="superadmin")
    captured: dict = {}
    row = _document_row()

    def _fake_list_documents(**kwargs):
        captured.update(kwargs)
        return [row]

    monkeypatch.setattr(documents_route.db_client, "list_documents", _fake_list_documents)
    client = TestClient(app)
    response = client.get(
        "/api/documents",
        params={
            "municipality": "dallas",
            "status": "active",
            "authority": "municipal",
            "doc_type": "building_code",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["doc_id"] == "dallas-building-code"
    assert body[0]["document_status"] == "active"
    assert captured == {
        "municipality": "dallas",
        "status": "active",
        "authority_level": "municipal",
        "doc_type": "building_code",
    }


def test_list_documents_requires_auth() -> None:
    """GET /documents with no credentials returns 401 (migration-045 auth-gate —
    this route had no auth at all before this fix)."""
    app.dependency_overrides.clear()  # remove this file's autouse default user
    client = TestClient(app)
    response = client.get("/api/documents")
    assert response.status_code == 401


def test_list_documents_scopes_to_own_library_for_regular_user(monkeypatch) -> None:
    """A non-staff caller gets list_documents_for_user, never the full corpus —
    the exposure this migration closes."""
    from api.routes import documents as documents_route

    user = _override_user(role="member")
    captured: dict = {}

    def _fake_list_for_user(user_id, **kwargs):
        captured["user_id"] = user_id
        captured.update(kwargs)
        return [_document_row("my-project-doc")]

    monkeypatch.setattr(documents_route.db_client, "list_documents", lambda **_k: (_ for _ in ()).throw(
        AssertionError("regular user must not hit the unscoped full-corpus query")
    ))
    monkeypatch.setattr(documents_route.db_client, "list_documents_for_user", _fake_list_for_user)

    client = TestClient(app)
    response = client.get("/api/documents", params={"municipality": "dallas"})

    assert response.status_code == 200
    assert captured["user_id"] == user["user_id"]
    assert captured["municipality"] == "dallas"


def test_list_documents_scope_mine_forces_personal_view_for_superadmin(monkeypatch) -> None:
    """?scope=mine makes a superadmin's own Document Library show their own
    documents, not the entire corpus (the corpus browser is a separate page)."""
    from api.routes import documents as documents_route

    user = _override_user(role="superadmin")
    captured: dict = {}

    monkeypatch.setattr(documents_route.db_client, "list_documents", lambda **_k: (_ for _ in ()).throw(
        AssertionError("scope=mine must bypass the superadmin full-corpus path")
    ))
    monkeypatch.setattr(
        documents_route.db_client,
        "list_documents_for_user",
        lambda user_id, **kwargs: captured.update({"user_id": user_id}) or [],
    )

    client = TestClient(app)
    response = client.get("/api/documents", params={"scope": "mine"})

    assert response.status_code == 200
    assert captured["user_id"] == user["user_id"]


def test_list_documents_rejects_invalid_authority_filter() -> None:
    """FastAPI should return 422 for invalid authority values."""
    client = TestClient(app)
    response = client.get("/api/documents", params={"authority": "city"})
    assert response.status_code == 422
    assert isinstance(response.json().get("detail"), str)


def test_get_document_detail_returns_chunk_count(monkeypatch) -> None:
    """GET /documents/{doc_id} should return detail metadata and chunk count."""
    from api.routes import documents as documents_route

    row = _document_row("tx-electrical-statute")
    monkeypatch.setattr(
        documents_route.db_client,
        "get_document_by_doc_id",
        lambda doc_id: row if doc_id == "tx-electrical-statute" else None,
    )
    monkeypatch.setattr(documents_route.db_client, "count_chunks", lambda _doc_uuid: 42)

    client = TestClient(app)
    response = client.get("/api/documents/tx-electrical-statute")

    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == "tx-electrical-statute"
    assert body["chunk_count"] == 42
    assert body["checksum_sha256"] == "abc123"


def test_get_document_detail_404_when_missing(monkeypatch) -> None:
    """GET /documents/{doc_id} should return 404 for unknown doc_id."""
    from api.routes import documents as documents_route

    monkeypatch.setattr(
        documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: None
    )

    client = TestClient(app)
    response = client.get("/api/documents/missing-doc")

    assert response.status_code == 404
    assert "Document not found" in response.json()["detail"]


def _tier3_row(*, uploaded_by, visibility: str, project_id=None) -> dict:
    row = _document_row("project-private-doc")
    row["source_tier"] = 3
    row["uploaded_by"] = uploaded_by
    row["visibility"] = visibility
    row["project_id"] = project_id or uuid4()
    return row


def test_get_document_detail_403_for_others_private_tier3_doc(monkeypatch) -> None:
    """A 'private' tier-3 doc is invisible to anyone but its uploader — the
    exact cross-tenant exposure migration 045 closes."""
    from api.routes import documents as documents_route

    viewer = _override_user(role="member")
    row = _tier3_row(uploaded_by=uuid4(), visibility="private")
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)

    client = TestClient(app)
    response = client.get("/api/documents/project-private-doc")

    assert response.status_code == 403
    assert viewer["user_id"] != row["uploaded_by"]


def test_get_document_detail_allows_owner_for_private_tier3_doc(monkeypatch) -> None:
    """The uploader can always see their own private document."""
    from api.routes import documents as documents_route

    viewer = _override_user(role="member")
    row = _tier3_row(uploaded_by=viewer["user_id"], visibility="private")
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)
    monkeypatch.setattr(documents_route.db_client, "count_chunks", lambda _uuid: 3)

    client = TestClient(app)
    response = client.get("/api/documents/project-private-doc")

    assert response.status_code == 200


def test_get_document_detail_allows_team_member_for_team_visibility_doc(monkeypatch) -> None:
    """A 'team' tier-3 doc is visible to a fellow project member (not just the uploader)."""
    from api.routes import documents as documents_route

    _override_user(role="member")
    row = _tier3_row(uploaded_by=uuid4(), visibility="team")
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)
    monkeypatch.setattr(documents_route.db_client, "count_chunks", lambda _uuid: 3)
    monkeypatch.setattr(
        documents_route.db_client, "get_project_role", lambda _pid, _uid: "editor"
    )

    client = TestClient(app)
    response = client.get("/api/documents/project-private-doc")

    assert response.status_code == 200


def test_get_document_detail_403_for_non_member_on_team_visibility_doc(monkeypatch) -> None:
    """'team' visibility means the project team, not everyone — a non-member is still blocked."""
    from api.routes import documents as documents_route

    _override_user(role="member")
    row = _tier3_row(uploaded_by=uuid4(), visibility="team")
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)
    monkeypatch.setattr(documents_route.db_client, "get_project_role", lambda _pid, _uid: None)

    client = TestClient(app)
    response = client.get("/api/documents/project-private-doc")

    assert response.status_code == 403


def test_download_document_success(monkeypatch, tmp_path) -> None:
    """GET /documents/{doc_id}/download streams the stored file for a visible doc."""
    from api.routes import documents as documents_route

    stored = tmp_path / "plan.pdf"
    stored.write_bytes(b"%PDF-1.4 fake content")
    row = _document_row("dallas-building-code")
    row["local_path"] = str(stored)
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)

    client = TestClient(app)
    response = client.get("/api/documents/dallas-building-code/download")

    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 fake content"


def test_download_document_403_for_private_others_doc(monkeypatch, tmp_path) -> None:
    """Download follows the same visibility rule as the detail route — no
    bypassing the visibility check via the file endpoint."""
    from api.routes import documents as documents_route

    stored = tmp_path / "private.pdf"
    stored.write_bytes(b"secret")
    row = _tier3_row(uploaded_by=uuid4(), visibility="private")
    row["local_path"] = str(stored)
    _override_user(role="member")
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)

    client = TestClient(app)
    response = client.get("/api/documents/project-private-doc/download")

    assert response.status_code == 403


def test_download_document_404_when_no_local_file(monkeypatch) -> None:
    """A document with no stored file (e.g. tier-1 scraped from a URL) 404s
    rather than erroring on a missing path."""
    from api.routes import documents as documents_route

    row = _document_row("dallas-building-code")
    row["local_path"] = None
    monkeypatch.setattr(documents_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)

    client = TestClient(app)
    response = client.get("/api/documents/dallas-building-code/download")

    assert response.status_code == 404


def test_document_status_counts_response_shape(monkeypatch) -> None:
    """GET /documents/status should return grouped counts and total."""
    from api.routes import documents as documents_route

    def _fake_status_counts(**_kwargs):
        return [
            {"document_status": "active", "count": 8},
            {"document_status": "draft", "count": 2},
        ]

    monkeypatch.setattr(
        documents_route.db_client, "get_document_status_counts", _fake_status_counts
    )

    client = TestClient(app)
    response = client.get(
        "/api/documents/status",
        params={"municipality": "dallas", "authority": "municipal"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["municipality"] == "dallas"
    assert body["authority"] == "municipal"
    assert body["total_documents"] == 10
    assert body["counts"] == [
        {"status": "active", "count": 8},
        {"status": "draft", "count": 2},
    ]


def test_patch_admin_document_updates_metadata(monkeypatch) -> None:
    """PATCH /admin/documents/{doc_id} applies governance metadata updates."""
    from api.routes import admin as admin_route

    captured: dict = {}
    row = _document_row("tx-admin-doc")

    def _fake_update(doc_id: str, **kwargs):
        captured["doc_id"] = doc_id
        captured.update(kwargs)
        row["document_status"] = kwargs["document_status"]
        row["retrieval_weight"] = Decimal("0.55")
        return row

    monkeypatch.setattr(
        admin_route.db_client, "update_document_admin_fields", _fake_update
    )
    monkeypatch.setattr(admin_route.db_client, "count_chunks", lambda _doc_uuid: 12)

    client = TestClient(app)
    response = client.patch(
        "/api/admin/documents/tx-admin-doc",
        json={"document_status": "draft", "retrieval_weight": 0.55},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "update_document_metadata"
    assert body["document"]["doc_id"] == "tx-admin-doc"
    assert body["document"]["document_status"] == "draft"
    assert body["document"]["chunk_count"] == 12
    assert captured == {
        "doc_id": "tx-admin-doc",
        "document_status": "draft",
        "is_current": None,
        "retrieval_weight": 0.55,
        "review_due": None,
    }


def test_patch_admin_document_requires_token_when_configured(monkeypatch) -> None:
    """PATCH /admin/documents/{doc_id} returns 403 when token is configured and missing."""
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")
    client = TestClient(app)
    response = client.patch(
        "/api/admin/documents/tx-admin-doc",
        json={"document_status": "draft"},
    )
    assert response.status_code == 403
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)


def test_patch_admin_document_requires_allowed_role(monkeypatch) -> None:
    """PATCH /admin/documents/{doc_id} enforces configured admin role allowlist."""
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("API_ADMIN_ALLOWED_ROLES", "admin,owner")
    client = TestClient(app)
    response = client.patch(
        "/api/admin/documents/tx-admin-doc",
        json={"document_status": "draft"},
        headers={"X-Admin-Token": "secret-token", "X-Admin-Role": "viewer"},
    )
    assert response.status_code == 403
    assert "Insufficient admin role" in response.json()["detail"]


def test_patch_admin_document_allows_valid_role(monkeypatch) -> None:
    """PATCH /admin/documents/{doc_id} passes with valid token + role headers."""
    from api.routes import admin as admin_route

    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("API_ADMIN_ALLOWED_ROLES", "admin,owner")
    monkeypatch.setattr(
        admin_route.db_client,
        "update_document_admin_fields",
        lambda _doc_id, **_k: _document_row("tx-admin-doc"),
    )
    monkeypatch.setattr(admin_route.db_client, "count_chunks", lambda _doc_uuid: 9)

    client = TestClient(app)
    response = client.patch(
        "/api/admin/documents/tx-admin-doc",
        json={"document_status": "draft"},
        headers={"X-Admin-Token": "secret-token", "X-Admin-Role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["document"]["doc_id"] == "tx-admin-doc"


def test_patch_admin_document_404_when_missing(monkeypatch) -> None:
    """PATCH /admin/documents/{doc_id} should return 404 for unknown doc_id."""
    from api.routes import admin as admin_route

    monkeypatch.setattr(
        admin_route.db_client, "update_document_admin_fields", lambda _doc_id, **_k: None
    )

    client = TestClient(app)
    response = client.patch(
        "/api/admin/documents/missing-doc",
        json={"document_status": "draft"},
    )

    assert response.status_code == 404
    assert "Document not found" in response.json()["detail"]


def test_supersede_admin_document_success(monkeypatch) -> None:
    """POST /admin/documents/{doc_id}/supersede should mark source as superseded."""
    from api.routes import admin as admin_route

    row = _document_row("old-doc")
    row["document_status"] = "superseded"
    row["is_current"] = False
    row["superseded_by"] = uuid4()
    row["retrieval_weight"] = Decimal("0.10")

    captured: dict = {}

    def _fake_supersede(doc_id: str, replacement_doc_id: str, **kwargs):
        captured["doc_id"] = doc_id
        captured["replacement_doc_id"] = replacement_doc_id
        captured.update(kwargs)
        return row

    monkeypatch.setattr(admin_route.db_client, "supersede_document", _fake_supersede)
    monkeypatch.setattr(admin_route.db_client, "count_chunks", lambda _doc_uuid: 42)

    client = TestClient(app)
    response = client.post(
        "/api/admin/documents/old-doc/supersede",
        json={"replacement_doc_id": "new-doc", "superseded_weight": 0.1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "supersede_document"
    assert body["document"]["document_status"] == "superseded"
    assert body["document"]["is_current"] is False
    assert captured == {
        "doc_id": "old-doc",
        "replacement_doc_id": "new-doc",
        "superseded_weight": 0.1,
    }


def test_supersede_admin_document_rejects_invalid_request(monkeypatch) -> None:
    """POST /admin/documents/{doc_id}/supersede returns 400 on invalid supersession."""
    from api.routes import admin as admin_route

    def _raise_value_error(_doc_id: str, _replacement_doc_id: str, **_kwargs):
        raise ValueError("Replacement document not found: new-doc")

    monkeypatch.setattr(admin_route.db_client, "supersede_document", _raise_value_error)

    client = TestClient(app)
    response = client.post(
        "/api/admin/documents/old-doc/supersede",
        json={"replacement_doc_id": "new-doc"},
    )

    assert response.status_code == 400
    assert "Replacement document not found" in response.json()["detail"]


def test_purge_project_upload_success(monkeypatch) -> None:
    """POST /admin/documents/{doc_id}/purge-project-upload removes chunks and tombstones row."""
    from api.routes import admin as admin_route

    row = _document_row("project-doc-1")
    row["source_tier"] = 3
    row["local_path"] = "documents/raw/project-doc-1.html"
    updated_row = dict(row)
    updated_row["document_status"] = "repealed"
    updated_row["is_current"] = False
    updated_row["retrieval_weight"] = Decimal("0.00")
    captured: dict = {}
    captured_audit: dict = {}

    monkeypatch.setattr(admin_route.db_client, "get_document_by_doc_id", lambda doc_id: row if doc_id == "project-doc-1" else None)
    monkeypatch.setattr(
        admin_route.db_client,
        "delete_chunks_for_document",
        lambda _doc_uuid: 17,
    )
    monkeypatch.setattr(admin_route, "_remove_local_raw_file", lambda _path: True)
    monkeypatch.setattr(
        admin_route.db_client,
        "update_document_admin_fields",
        lambda doc_id, **kwargs: captured.update({"doc_id": doc_id, **kwargs}) or updated_row,
    )
    monkeypatch.setattr(
        admin_route.db_client,
        "insert_purge_audit_log",
        lambda **kwargs: captured_audit.update(kwargs) or {"id": uuid4()},
    )
    monkeypatch.setattr(admin_route.db_client, "count_chunks", lambda _doc_uuid: 0)

    client = TestClient(app)
    response = client.post(
        "/api/admin/documents/project-doc-1/purge-project-upload",
        headers={"X-Admin-Role": "owner", "X-Admin-User": "qa-user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "purge_project_upload"
    assert body["document"]["document_status"] == "repealed"
    assert body["document"]["chunk_count"] == 0
    assert captured == {
        "doc_id": "project-doc-1",
        "document_status": "repealed",
        "is_current": False,
        "retrieval_weight": 0.0,
    }
    assert captured_audit == {
        "doc_id": "project-doc-1",
        "document_id": row["id"],
        "actor_identity": "qa-user",
        "actor_role": "owner",
        "source_tier": 3,
        "deleted_chunk_count": 17,
        "local_file_deleted": True,
    }


def test_purge_project_upload_rejects_non_project_tier(monkeypatch) -> None:
    """Purge route should require elevated role for non-project tiers."""
    from api.routes import admin as admin_route

    row = _document_row("city-code-doc")
    row["source_tier"] = 1
    monkeypatch.setattr(admin_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)

    client = TestClient(app)
    response = client.post("/api/admin/documents/city-code-doc/purge-project-upload")

    assert response.status_code == 403
    assert "requires elevated role" in response.json()["detail"]


def test_purge_project_upload_allows_non_project_tier_with_elevated_role(monkeypatch) -> None:
    """Non-tier-3 purge should pass when caller has elevated purge role."""
    from api.routes import admin as admin_route

    row = _document_row("city-code-doc")
    row["source_tier"] = 1
    updated_row = dict(row)
    updated_row["document_status"] = "repealed"
    updated_row["is_current"] = False
    updated_row["retrieval_weight"] = Decimal("0.00")
    monkeypatch.setenv("API_PURGE_ANY_TIER_ROLES", "owner,superadmin")
    monkeypatch.setattr(admin_route.db_client, "get_document_by_doc_id", lambda _doc_id: row)
    monkeypatch.setattr(admin_route.db_client, "delete_chunks_for_document", lambda _doc_uuid: 3)
    monkeypatch.setattr(admin_route, "_remove_local_raw_file", lambda _path: True)
    monkeypatch.setattr(
        admin_route.db_client,
        "update_document_admin_fields",
        lambda _doc_id, **_kwargs: updated_row,
    )
    monkeypatch.setattr(
        admin_route.db_client,
        "insert_purge_audit_log",
        lambda **_kwargs: {"id": uuid4()},
    )
    monkeypatch.setattr(admin_route.db_client, "count_chunks", lambda _doc_uuid: 0)

    client = TestClient(app)
    response = client.post(
        "/api/admin/documents/city-code-doc/purge-project-upload",
        headers={"X-Admin-Role": "owner"},
    )

    assert response.status_code == 200
    assert response.json()["action"] == "purge_project_upload"


def test_document_summary_serializes_how_to_transcript_metadata() -> None:
    """Regression: a how-to transcript doc (migration 031: authority_level=
    'educational', doc_type='how_to_video') must serialize without a
    ValidationError — the /api/documents crash found verifying C2."""
    from api.schemas import DocumentSummaryResponse

    resp = DocumentSummaryResponse(
        id=uuid4(), doc_id="how-to-abc123",
        source_url="https://www.youtube.com/watch?v=abc123",
        municipality="national", authority_level="educational",
        doc_type="how_to_video", subject_tags=["install_gfci_outlet"],
        document_status="active", is_current=True, effective_date=None,
        review_due=None, retrieval_weight=1.0, updated_at=datetime.now(timezone.utc),
    )
    assert resp.authority_level == "educational"
    assert resp.doc_type == "how_to_video"
