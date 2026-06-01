"""
tests/test_documents_routes.py — API tests for documents routes
===============================================================
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app


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
    }


def test_list_documents_applies_all_filters(monkeypatch) -> None:
    """GET /documents should pass municipality/status/authority/doc_type filters."""
    from api.routes import documents as documents_route

    captured: dict = {}
    row = _document_row()

    def _fake_list_documents(**kwargs):
        captured.update(kwargs)
        return [row]

    monkeypatch.setattr(documents_route.db_client, "list_documents", _fake_list_documents)
    client = TestClient(app)
    response = client.get(
        "/documents",
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


def test_list_documents_rejects_invalid_authority_filter() -> None:
    """FastAPI should return 422 for invalid authority values."""
    client = TestClient(app)
    response = client.get("/documents", params={"authority": "city"})
    assert response.status_code == 422


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
    response = client.get("/documents/tx-electrical-statute")

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
    response = client.get("/documents/missing-doc")

    assert response.status_code == 404
    assert "Document not found" in response.json()["detail"]


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
        "/documents/status",
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
        "/admin/documents/tx-admin-doc",
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
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")
    client = TestClient(app)
    response = client.patch(
        "/admin/documents/tx-admin-doc",
        json={"document_status": "draft"},
    )
    assert response.status_code == 403
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)


def test_patch_admin_document_404_when_missing(monkeypatch) -> None:
    """PATCH /admin/documents/{doc_id} should return 404 for unknown doc_id."""
    from api.routes import admin as admin_route

    monkeypatch.setattr(
        admin_route.db_client, "update_document_admin_fields", lambda _doc_id, **_k: None
    )

    client = TestClient(app)
    response = client.patch(
        "/admin/documents/missing-doc",
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
        "/admin/documents/old-doc/supersede",
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
        "/admin/documents/old-doc/supersede",
        json={"replacement_doc_id": "new-doc"},
    )

    assert response.status_code == 400
    assert "Replacement document not found" in response.json()["detail"]
