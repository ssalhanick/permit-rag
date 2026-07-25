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
        # Mirrors the real RetrievalResult property: only chunks the reranker
        # kept are prompted, so rejected ones are never billed or cited.
        passing_chunks=[c for c in chunks if not c.get("filtered_out")],
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
    import rag.generator as generator_module
    import rag.permit_classifier as classifier_module
    from api.routes import query as query_route
    from db import client as db_client

    monkeypatch.setattr(db_client, "insert_query_log", lambda **kwargs: {})
    monkeypatch.setattr(query_route, "retrieve_with_project", lambda *_a, **_k: _retrieval_result())
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

    app.dependency_overrides[query_route.get_current_user] = lambda: {
        "user_id": uuid4(),
        "role": "member",
        "username": "tester"
    }

    try:
        client = TestClient(app)
        response = client.post(
            "/api/query/answer",
            json={"query": "garage addition with panel and bathroom", "top_k": 5, "municipality": "dallas"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["permit_types"] == ["building", "electrical", "plumbing"]
        assert len(body["citations"]) == 3
        assert all(c["found_in_context"] is True for c in body["citations"])
        assert body["ahj_disclaimer"]["learn_more_url"] == "https://example.org/permits"
    finally:
        app.dependency_overrides.clear()


def test_query_answer_classifier_failure_falls_back_to_empty_list(monkeypatch) -> None:
    """Classifier failure should not break route; permit_types should default to []."""
    import rag.generator as generator_module
    import rag.permit_classifier as classifier_module
    from api.routes import query as query_route
    from db import client as db_client

    monkeypatch.setattr(db_client, "insert_query_log", lambda **kwargs: {})
    monkeypatch.setattr(query_route, "retrieve_with_project", lambda *_a, **_k: _retrieval_result())
    monkeypatch.setattr(generator_module, "generate_answer", lambda *_a, **_k: _generation_result())

    def _raise_classifier(*_args, **_kwargs):
        raise RuntimeError("classifier boom")

    monkeypatch.setattr(classifier_module, "classify_permit_types", _raise_classifier)
    monkeypatch.setattr(query_route, "get_jurisdiction", lambda _m: None)

    app.dependency_overrides[query_route.get_current_user] = lambda: {
        "user_id": uuid4(),
        "role": "member",
        "username": "tester"
    }

    try:
        client = TestClient(app)
        response = client.post(
            "/api/query/answer",
            json={"query": "garage addition with panel and bathroom", "top_k": 5, "municipality": "dallas"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["permit_types"] == []
        assert len(body["citations"]) == 3
    finally:
        app.dependency_overrides.clear()


def test_query_answer_empty_corpus_returns_200_abstain(monkeypatch) -> None:
    """Phase 4 query-UX: empty retrieval is a conversational 200 abstain, not a 422.

    A 200 also stays clear of the CloudFront concern that first drove this off 404
    (a 404 was rewritten to the SPA index.html) — a real 200 body is never rewritten.
    """
    from api.routes import query as query_route
    from db import client as db_client

    empty_result = SimpleNamespace(
        query="test",
        top_k=8,
        municipality=None,
        chunks=[],
        passing_chunks=[],
        num_results=0,
        top_similarity=0.0,
        mean_similarity=0.0,
        unique_documents=[],
        latency_ms=10,
    )
    monkeypatch.setattr(db_client, "insert_query_log", lambda **kwargs: {})
    monkeypatch.setattr(query_route, "retrieve_with_project", lambda *_a, **_k: empty_result)
    monkeypatch.setattr(query_route, "get_jurisdiction", lambda _m: None)

    app.dependency_overrides[query_route.get_current_user] = lambda: {
        "user_id": uuid4(),
        "role": "member",
        "username": "tester",
    }

    try:
        client = TestClient(app)
        response = client.post(
            "/api/query/answer",
            json={"query": "fence permit in Dallas", "top_k": 8},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["abstained"] is True
        assert body["answer"]                       # a conversational message
        assert body["citations"] == []
        assert body["ahj_disclaimer"]["text"]       # disclaimer still attached
    finally:
        app.dependency_overrides.clear()


def test_media_ref_responses_maps_curated_refs() -> None:
    """The route maps the plan's MediaRef objects onto the response models."""
    from api.routes.query import _media_ref_responses
    from rag.agents.media import MediaRef

    plan = SimpleNamespace(media_refs=[
        MediaRef(title="GFCI how-to", url="https://www.youtube.com/watch?v=a",
                 relevance_note="step by step"),
    ])
    out = _media_ref_responses(plan)
    assert len(out) == 1
    assert out[0].url == "https://www.youtube.com/watch?v=a"
    assert out[0].provider == "youtube"


def test_media_ref_responses_empty_when_absent() -> None:
    """A plan with no media_refs (non-diy / abstain) maps to an empty list."""
    from api.routes.query import _media_ref_responses

    assert _media_ref_responses(SimpleNamespace(media_refs=[])) == []
    assert _media_ref_responses(SimpleNamespace()) == []
