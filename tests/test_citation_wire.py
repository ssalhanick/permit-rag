"""
tests/test_citation_wire.py — Citation Verifier (#9) wired into the query path
=============================================================================
The Manager's wave-5 citation check runs on the live /query/answer path
(deterministic, no model). A clean answer flags nothing; an answer citing a
chunk retrieval never returned surfaces `unsupported_citations`. Fully mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app


def _chunk(doc_id: str, idx: int, content: str) -> dict:
    return {
        "id": uuid4(), "document_id": uuid4(), "doc_id": doc_id, "chunk_index": idx,
        "content": content, "municipality": "dallas", "authority_level": "municipal",
        "doc_type": "building_code", "document_status": "active", "source_tier": 1,
        "similarity": 0.88, "raw_similarity": 0.88, "reranked_score": 0.88,
        "provenance_weight": 1.0, "filtered_out": False,
    }


def _retrieval() -> SimpleNamespace:
    # Three chunks so the answer clears the grounding floor and actually
    # generates (fewer would abstain, skipping the citation check entirely).
    chunks = [
        _chunk("dallas-fence", 0,
               "A residential fence setback must be five feet from the property line."),
        _chunk("dallas-fence", 1,
               "Fence height in a residential zone may not exceed eight feet."),
        _chunk("dallas-permit", 2,
               "A building permit is required before construction begins."),
    ]
    return SimpleNamespace(
        query="dummy", top_k=5, municipality="dallas", chunks=chunks,
        passing_chunks=chunks, num_results=len(chunks), top_similarity=0.88,
        mean_similarity=0.85, unique_documents=["dallas-fence", "dallas-permit"],
        latency_ms=25,
    )


def _generation(answer: str, citations: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        answer=answer, citations=citations, model="claude-test",
        input_tokens=100, output_tokens=50, latency_ms=40, chunk_count=1,
    )


def _run(monkeypatch, answer: str, citations: list[dict]) -> dict:
    import rag.generator as generator_module
    import rag.permit_classifier as classifier_module
    from api.routes import query as query_route
    from db import client as db_client

    monkeypatch.setattr(db_client, "insert_query_log", lambda **kwargs: {})
    monkeypatch.setattr(query_route, "retrieve_with_project", lambda *_a, **_k: _retrieval())
    monkeypatch.setattr(generator_module, "generate_answer",
                        lambda *_a, **_k: _generation(answer, citations))
    monkeypatch.setattr(classifier_module, "classify_permit_types", lambda *_a, **_k: [])
    monkeypatch.setattr(query_route, "get_jurisdiction", lambda _m: None)
    app.dependency_overrides[query_route.get_current_user] = lambda: {
        "user_id": uuid4(), "role": "member", "username": "tester",
    }
    try:
        resp = TestClient(app).post(
            "/api/query/answer",
            json={"query": "fence setback in dallas", "top_k": 5, "municipality": "dallas"},
        )
        assert resp.status_code == 200
        return resp.json()
    finally:
        app.dependency_overrides.clear()


def test_clean_answer_flags_no_unsupported_citations(monkeypatch) -> None:
    """An answer citing a retrieved chunk it paraphrases surfaces nothing."""
    answer = "The residential fence setback must be five feet from the property line [dallas-fence, chunk 0]."
    citations = [{"doc_id": "dallas-fence", "chunk_index": 0, "found_in_context": True,
                  "municipality": "dallas", "authority_level": "municipal"}]
    body = _run(monkeypatch, answer, citations)
    assert body["unsupported_citations"] == []


def test_fabricated_citation_is_surfaced(monkeypatch) -> None:
    """A citation to a chunk retrieval never returned is flagged for the user."""
    answer = "Permit fees are $250 [plano-fees, chunk 9]."  # plano-fees not retrieved
    citations = [{"doc_id": "plano-fees", "chunk_index": 9, "found_in_context": False,
                  "municipality": "plano", "authority_level": "municipal"}]
    body = _run(monkeypatch, answer, citations)
    assert len(body["unsupported_citations"]) == 1
    assert "Permit fees are $250" in body["unsupported_citations"][0]
