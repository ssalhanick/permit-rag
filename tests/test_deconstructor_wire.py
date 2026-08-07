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
    # item 3: an all-empty union resets sub_retrievals so the plan takes the
    # single-answer path — one clean abstain, not N empty parts.
    assert st.sub_retrievals == []


# ── sub_retrievals — item 3's per-sub-question retrieval side channel ────


def test_fanout_populates_sub_retrievals_index_aligned() -> None:
    """Each sub-question's own, un-merged RetrievalResult lands in
    state.sub_retrievals, index-aligned with sub_questions — not the merged/
    deduped/capped pool _fanout_retrieval still returns for the existing path."""
    a1, b1 = _chunk(0.95), _chunk(0.7)

    def _retrieve(q, **_k):
        if q == "sub-a":
            return _result([a1], 10, query=q)
        return _result([b1], 12, query=q)

    st = _state(_retrieve, [SubQuestion(text="sub-a"), SubQuestion(text="sub-b")])
    mgr._run_retrieval(st)
    assert len(st.sub_retrievals) == 2
    assert [c["id"] for c in st.sub_retrievals[0].chunks] == [a1["id"]]
    assert [c["id"] for c in st.sub_retrievals[1].chunks] == [b1["id"]]


def test_fanout_records_none_for_a_failed_sub_question() -> None:
    """One sub-question's retrieval raising doesn't drop it from sub_retrievals
    — it's recorded as None so index alignment with sub_questions holds."""
    ok = _chunk(0.9)

    def _retrieve(q, **_k):
        if q == "sub-a":
            raise ConnectionError("pgvector down")
        return _result([ok], 5, query=q)

    st = _state(_retrieve, [SubQuestion(text="sub-a"), SubQuestion(text="sub-b")])
    mgr._run_retrieval(st)
    assert st.sub_retrievals[0] is None
    assert [c["id"] for c in st.sub_retrievals[1].chunks] == [ok["id"]]


def test_fanout_canonicalizes_sub_question_municipality() -> None:
    """A sub-question's own municipality is canonicalized before retrieval.

    Found 2026-08-07 via a live hand-check on Machine B: the Deconstructor's
    raw LLM output ("Fort Worth", "Plano", "Dallas" -- capitalized, unslugified)
    was passed straight to retrieve() -> get_jurisdiction_chain(), which does an
    exact-match lookup against the corpus's canonical lowercase/aliased ids
    (jurisdiction_ids.py's whole reason for existing, incl. the documented
    "fort-worth" -> "fortworth" collision). Every real sub-question with its own
    named municipality silently matched zero chunks. state.effective_municipality
    already goes through canonicalize() elsewhere (_resolve_municipality) --
    _fanout_retrieval was the one path that didn't.
    """
    seen_municipalities = []

    def _retrieve(q, *, municipality=None, **_k):
        seen_municipalities.append(municipality)
        return _result([_chunk(0.9)], 5, query=q)

    st = _state(
        _retrieve,
        [SubQuestion(text="a", municipality="Fort Worth"),
         SubQuestion(text="b", municipality="Plano")],
    )
    mgr._run_retrieval(st)
    assert seen_municipalities == ["fortworth", "plano"]


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
