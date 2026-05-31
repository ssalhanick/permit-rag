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
