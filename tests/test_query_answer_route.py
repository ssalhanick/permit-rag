"""
tests/test_query_answer_route.py — Regression tests for /query/answer
=====================================================================
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app


def _chunk(doc_id: str, chunk_index: int, content: str) -> dict:
    """Build one retrieval chunk row matching Query route expectations."""
    return {
        "id": uuid4(),
        "document_id": uuid4(),
        "doc_id": doc_id,
        "chunk_index": chunk_index,
        "content": content,
        "municipality": "dallas",
        "authority_level": "municipal",
        "doc_type": "building_code",
        "document_status": "active",
        "source_tier": 1,
        "similarity": 0.88,
        "raw_similarity": 0.88,
        "reranked_score": 0.88,
        "provenance_weight": 1.0,
        "filtered_out": False,
    }


def _retrieval_result() -> SimpleNamespace:
    """Build retrieval response object used by /query/answer route."""
    chunks = [
        _chunk("dallas-building", 0, "Building permit baseline text."),
        _chunk("dallas-electrical", 1, "Electrical permit panel upgrade text."),
        _chunk("dallas-plumbing", 2, "Plumbing permit bathroom addition text."),
    ]
    return SimpleNamespace(
        query="dummy",
        top_k=5,
        municipality="dallas",
        chunks=chunks,
        num_results=len(chunks),
        top_similarity=0.88,
        mean_similarity=0.85,
        unique_documents=["dallas-building", "dallas-electrical", "dallas-plumbing"],
        latency_ms=25,
    )


def _generation_result() -> SimpleNamespace:
    """Build generation response object used by /query/answer route."""
    return SimpleNamespace(
        answer=(
            "You need building, electrical, and plumbing permits in this scope "
            "[dallas-building, chunk 0] [dallas-electrical, chunk 1] [dallas-plumbing, chunk 2]."
        ),
        citations=[
            {
                "doc_id": "dallas-building",
                "chunk_index": 0,
                "found_in_context": True,
                "municipality": "dallas",
                "authority_level": "municipal",
            },
            {
                "doc_id": "dallas-electrical",
                "chunk_index": 1,
                "found_in_context": True,
                "municipality": "dallas",
                "authority_level": "municipal",
            },
            {
                "doc_id": "dallas-plumbing",
                "chunk_index": 2,
                "found_in_context": True,
                "municipality": "dallas",
                "authority_level": "municipal",
            },
        ],
        model="claude-test",
        input_tokens=100,
        output_tokens=50,
        latency_ms=40,
        chunk_count=3,
    )


def test_query_answer_returns_multi_permit_types_and_citations(monkeypatch) -> None:
    """Route should return permit_types + structured citations for multi-scope query."""
    from api.routes import query as query_route
    import rag.generator as generator_module
    import rag.permit_classifier as classifier_module
    from db import client as db_client

    monkeypatch.setattr(db_client, "insert_query_log", lambda **kwargs: {})
    monkeypatch.setattr(query_route, "retrieve", lambda *_a, **_k: _retrieval_result())
    monkeypatch.setattr(generator_module, "generate_answer", lambda *_a, **_k: _generation_result())
    monkeypatch.setattr(
        classifier_module,
        "classify_permit_types",
        lambda *_a, **_k: ["building", "electrical", "plumbing"],
    )
    monkeypatch.setattr(
        query_route,
        "get_jurisdiction",
        lambda _m: {"dept_url": "https://example.org/permits"},
    )

    client = TestClient(app)
    response = client.post(
        "/query/answer",
        json={"query": "garage addition with panel and bathroom", "top_k": 5, "municipality": "dallas"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["permit_types"] == ["building", "electrical", "plumbing"]
    assert len(body["citations"]) == 3
    assert all(c["found_in_context"] is True for c in body["citations"])
    assert body["ahj_disclaimer"]["learn_more_url"] == "https://example.org/permits"


def test_query_answer_classifier_failure_falls_back_to_empty_list(monkeypatch) -> None:
    """Classifier failure should not break route; permit_types should default to []."""
    from api.routes import query as query_route
    import rag.generator as generator_module
    import rag.permit_classifier as classifier_module
    from db import client as db_client

    monkeypatch.setattr(db_client, "insert_query_log", lambda **kwargs: {})
    monkeypatch.setattr(query_route, "retrieve", lambda *_a, **_k: _retrieval_result())
    monkeypatch.setattr(generator_module, "generate_answer", lambda *_a, **_k: _generation_result())

    def _raise_classifier(*_args, **_kwargs):
        raise RuntimeError("classifier boom")

    monkeypatch.setattr(classifier_module, "classify_permit_types", _raise_classifier)
    monkeypatch.setattr(query_route, "get_jurisdiction", lambda _m: None)

    client = TestClient(app)
    response = client.post(
        "/query/answer",
        json={"query": "garage addition with panel and bathroom", "top_k": 5, "municipality": "dallas"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["permit_types"] == []
    assert len(body["citations"]) == 3
