"""
tests/test_deconstructor_wire.py — Query Deconstructor (#5) fan-out in the Manager
=================================================================================
The retrieval wave fans out one search per sub-question and merges the union,
but stays byte-identical on the single-question (simple) path. Retrieval is a
stub — no DB, no model.
"""

from __future__ import annotations

from uuid import uuid4

from rag.agents import manager as mgr
from rag.agents.deconstructor import SubQuestion
from rag.retriever import RetrievalResult


def _chunk(score: float) -> dict:
    return {
        "id": uuid4(), "doc_id": "doc", "chunk_index": 0,
        "similarity": score, "reranked_score": score, "filtered_out": False,
    }


def _result(chunks: list[dict], latency: int, query: str = "q") -> RetrievalResult:
    return RetrievalResult(
        query=query, chunks=chunks, top_k=8, municipality="dallas", latency_ms=latency,
    )


def _state(retrieve, sub_questions, top_k=8):
    st = mgr._PlanState(
        request=mgr.ManagerRequest(query="orig", top_k=top_k),
        deps=mgr.ManagerDeps(retrieve=retrieve),
        store=mgr.ArtifactStore(),
        governor=mgr.BudgetGovernor(),
    )
    st.effective_municipality = "dallas"
    st.sub_questions = sub_questions
    return st


def test_single_question_path_calls_retrieve_once_with_original(monkeypatch) -> None:
    """One sub-question ⇒ the unchanged single retrieval on the original query."""
    calls = []

    def _retrieve(q, **_k):
        calls.append(q)
        return _result([_chunk(0.9)], 10)

    st = _state(_retrieve, [SubQuestion(text="orig")])
    mgr._run_retrieval(st)
    assert calls == ["orig"]  # no fan-out, original query only
    assert st.store.get(st.retrieval_ref).num_results == 1


def test_fanout_merges_and_dedupes(monkeypatch) -> None:
    """Two sub-questions ⇒ one retrieval each, union deduped by chunk id."""
    shared = _chunk(0.8)
    a1, b1 = _chunk(0.95), _chunk(0.7)

    def _retrieve(q, **_k):
        if q == "sub-a":
            return _result([a1, shared], 10)
        return _result([shared, b1], 12)  # shared repeats

    st = _state(_retrieve, [SubQuestion(text="sub-a"), SubQuestion(text="sub-b")])
    mgr._run_retrieval(st)
    result = st.store.get(st.retrieval_ref)
    ids = [c["id"] for c in result.chunks]
    assert len(ids) == 3 and len(set(ids)) == 3  # shared chunk merged once
    assert ids[0] == a1["id"]  # re-ranked by score, highest first
    assert result.latency_ms == 22  # summed across sub-questions


def test_fanout_caps_at_top_k(monkeypatch) -> None:
    """The merged union is capped at top_k so context/grounding are unchanged."""
    def _retrieve(q, **_k):
        return _result([_chunk(0.9) for _ in range(5)], 5)

    st = _state(_retrieve, [SubQuestion(text="a"), SubQuestion(text="b")], top_k=3)
    mgr._run_retrieval(st)
    assert st.store.get(st.retrieval_ref).num_results == 3


def test_fanout_empty_falls_back_to_single(monkeypatch) -> None:
    """If every sub-question returns nothing, fall back to single retrieval."""
    calls = []

    def _retrieve(q, **_k):
        calls.append(q)
        return _result([], 1)

    st = _state(_retrieve, [SubQuestion(text="sub-a"), SubQuestion(text="sub-b")])
    mgr._run_retrieval(st)
    # both sub-questions tried (empty), then the single path on the original query
    assert calls == ["sub-a", "sub-b", "orig"]


def test_deconstruct_step_skips_explicit_chunk_ids() -> None:
    """A chunk-id request bypasses deconstruction (no sub-questions set)."""
    st = _state(lambda *a, **k: None, [])
    st.request.chunk_ids = ["11111111-1111-1111-1111-111111111111"]
    mgr._deconstruct(st)
    assert st.sub_questions == []


def test_deconstruct_failure_leaves_single_path(monkeypatch) -> None:
    """A deconstructor error degrades to the single-question path, never raises."""
    def _boom(_q):
        raise RuntimeError("model down")

    monkeypatch.setattr(mgr, "_agent", lambda name: _boom)
    st = _state(lambda *a, **k: None, [])
    mgr._deconstruct(st)
    assert st.sub_questions == []
