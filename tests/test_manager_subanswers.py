"""
tests/test_manager_subanswers.py — item 3: per-sub-question compound answers
================================================================================
``_generate_subanswers`` grounds, generates, and cites each sub-question of a
fanned-out compound query independently, instead of one call over a merged/
top-k-capped chunk pool that could crowd a sub-intent's chunks out before
generation ever ran (see ``_fanout_retrieval``/``_check_grounding`` in
``rag/agents/manager.py``).

Drives the plan state directly (same style as ``test_deconstructor_wire.py``)
through the real ``_run_retrieval`` -> ``_check_grounding`` -> ``_generate`` ->
``_verify_citations`` sequence, rather than the full ``run_query_plan`` —
``query_deconstructor``'s own LLM-gated splitting isn't what's under test
here; ``state.sub_questions`` is set directly instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from rag.agents import registry
from rag.agents.deconstructor import SubQuestion
from rag.agents.manager import (
    MAX_SUBQUESTIONS_FOR_GENERATION,
    ArtifactStore,
    BudgetGovernor,
    ManagerDeps,
    ManagerRequest,
    _check_grounding,
    _generate,
    _PlanState,
    _run_retrieval,
    _verify_citations,
)
from rag.agents.registry import AgentSpec
from rag.retriever import RetrievalResult


def _chunk(doc_id: str, index: int, *, municipality: str = "plano") -> dict:
    return {
        "id": uuid4(), "doc_id": doc_id, "chunk_index": index,
        "content": f"text-{doc_id}", "municipality": municipality,
        "similarity": 0.9, "reranked_score": 0.9, "filtered_out": False,
    }


def _retrieval(chunks: list[dict], *, query: str) -> RetrievalResult:
    return RetrievalResult(query=query, chunks=chunks, top_k=8, municipality="plano", latency_ms=5)


def _state(sub_questions: list[SubQuestion], retrieve, **deps_overrides) -> _PlanState:
    defaults = {"min_chunks": 1, "min_top_sim": 0.0, "min_municipality_match_chunks": 0}
    defaults.update(deps_overrides)
    st = _PlanState(
        request=ManagerRequest(query="compound q", municipality="plano", top_k=8),
        deps=ManagerDeps(retrieve=retrieve, **defaults),
        store=ArtifactStore(),
        governor=BudgetGovernor(),
    )
    st.effective_municipality = "plano"
    st.sub_questions = sub_questions
    return st


def _run_through_generation(st: _PlanState) -> None:
    """The real wave-2/wave-4 sequence a compound query actually takes."""
    _run_retrieval(st)
    _check_grounding(st)
    _generate(st)


@pytest.fixture()
def stub_generator(monkeypatch: pytest.MonkeyPatch):
    """answer_generator whose citation always points at the first chunk it was
    actually handed — makes cross-contamination checkable by doc_id."""
    saved = registry.get_or_none("answer_generator")

    def _generate_stub(query, chunks, **_k):
        cited = chunks[0] if chunks else None
        answer = f"Answer for {query}."
        citations = []
        if cited:
            answer += f" [{cited['doc_id']}, chunk {cited['chunk_index']}]"
            citations = [{
                "doc_id": cited["doc_id"], "chunk_index": cited["chunk_index"],
                "found_in_context": True,
            }]
        return SimpleNamespace(
            answer=answer, citations=citations, model="claude-test",
            input_tokens=10, output_tokens=5, latency_ms=8, chunk_count=len(chunks),
        )

    registry.register(AgentSpec(name="answer_generator", callable=_generate_stub), replace=True)
    yield
    if saved is not None:
        registry.register(saved, replace=True)


def test_mixed_sub_answers_no_citation_cross_contamination(stub_generator) -> None:
    """3-part compound query, 2 grounded + 1 abstained — each part's citations
    only ever cite the chunks that part itself retrieved, never another's."""
    setback_chunk = _chunk("setback-doc", 0)
    height_chunk = _chunk("height-doc", 0)

    def _retrieve(q, **_k):
        if q == "setback question":
            return _retrieval([setback_chunk], query=q)
        if q == "height question":
            return _retrieval([height_chunk], query=q)
        return _retrieval([], query=q)  # electrical sub-question: nothing retrieved

    st = _state(
        [SubQuestion(text="setback question"),
         SubQuestion(text="height question"),
         SubQuestion(text="electrical question")],
        _retrieve,
    )
    _run_through_generation(st)
    _verify_citations(st)

    assert len(st.sub_answers) == 3
    setback_sa, height_sa, electrical_sa = st.sub_answers

    assert setback_sa.abstained is False
    assert height_sa.abstained is False
    assert electrical_sa.abstained is True
    assert electrical_sa.abstain_message
    assert electrical_sa.answer is None

    assert [c["doc_id"] for c in setback_sa.citations] == ["setback-doc"]
    assert [c["doc_id"] for c in height_sa.citations] == ["height-doc"]
    assert electrical_sa.citations == []

    # Partial success is not a top-level abstain — this is the whole point.
    assert st.abstained is False
    assert st.generation_ref is not None


def test_all_subquestions_abstaining_sets_top_level_abstain() -> None:
    """Only when every part fails does the compound query abstain overall.

    Each sub-question retrieves *something* (so the union isn't empty and
    fan-out doesn't fall back to the single-question path — that's the
    all-empty case, covered separately in test_deconstructor_wire.py), but
    below an unreachable min_chunks floor, so every part still abstains.
    """
    def _retrieve(q, **_k):
        return _retrieval([_chunk(f"{q}-doc", 0)], query=q)

    st = _state(
        [SubQuestion(text="a"), SubQuestion(text="b")], _retrieve, min_chunks=99,
    )
    _run_through_generation(st)

    assert st.abstained is True
    assert st.generation_ref is None
    assert len(st.sub_answers) == 2
    assert all(sa.abstained for sa in st.sub_answers)
    assert st.abstain_message


def test_one_grounded_one_retrieval_failure(stub_generator) -> None:
    """A sub-question whose own retrieval raised (sub_retrievals entry is None)
    is treated as abstained, not as a crash — the other part still answers."""
    ok_chunk = _chunk("ok-doc", 0)

    def _retrieve(q, **_k):
        if q == "boom":
            raise ConnectionError("pgvector down")
        return _retrieval([ok_chunk], query=q)

    st = _state([SubQuestion(text="boom"), SubQuestion(text="fine")], _retrieve)
    _run_through_generation(st)

    boom_sa, fine_sa = st.sub_answers
    assert boom_sa.abstained is True
    assert fine_sa.abstained is False
    assert st.abstained is False


@pytest.fixture()
def stub_generator_with_fabrication(monkeypatch: pytest.MonkeyPatch):
    """One sub-question's answer cites a chunk it was never actually handed —
    a fabrication the real (deterministic, use_llm=False) citation_verifier
    should catch and attribute to exactly that sub-answer."""
    saved = registry.get_or_none("answer_generator")

    def _generate_stub(query, chunks, **_k):
        if query == "setback question":
            return SimpleNamespace(
                answer="Setback is 25 feet. [fabricated-doc, chunk 99]",
                citations=[{"doc_id": "fabricated-doc", "chunk_index": 99,
                            "found_in_context": False}],
                model="claude-test", input_tokens=10, output_tokens=5,
                latency_ms=8, chunk_count=len(chunks),
            )
        cited = chunks[0]
        return SimpleNamespace(
            answer=f"Height is 35 feet. [{cited['doc_id']}, chunk {cited['chunk_index']}]",
            citations=[{"doc_id": cited["doc_id"], "chunk_index": cited["chunk_index"],
                        "found_in_context": True}],
            model="claude-test", input_tokens=10, output_tokens=5,
            latency_ms=8, chunk_count=len(chunks),
        )

    registry.register(AgentSpec(name="answer_generator", callable=_generate_stub), replace=True)
    yield
    if saved is not None:
        registry.register(saved, replace=True)


def test_fabricated_citation_attributed_to_correct_subanswer(
    stub_generator_with_fabrication,
) -> None:
    setback_chunk = _chunk("setback-doc", 0)
    height_chunk = _chunk("height-doc", 0)

    def _retrieve(q, **_k):
        if q == "setback question":
            return _retrieval([setback_chunk], query=q)
        return _retrieval([height_chunk], query=q)

    st = _state(
        [SubQuestion(text="setback question"), SubQuestion(text="height question")],
        _retrieve,
    )
    _run_through_generation(st)
    _verify_citations(st)

    setback_sa, height_sa = st.sub_answers
    assert setback_sa.unsupported_citations  # the fabrication, caught
    assert height_sa.unsupported_citations == []  # not leaked onto the clean part


def test_max_subquestions_cap_truncates_generation(stub_generator) -> None:
    """The Deconstructor has no hard cap on sub-question count; generation
    does, so an unbounded compound query can't multiply LLM cost unbounded."""
    def _retrieve(q, **_k):
        return _retrieval([_chunk(f"{q}-doc", 0)], query=q)

    subs = [SubQuestion(text=f"q{i}") for i in range(MAX_SUBQUESTIONS_FOR_GENERATION + 2)]
    st = _state(subs, _retrieve)
    _run_through_generation(st)

    assert len(st.sub_answers) == MAX_SUBQUESTIONS_FOR_GENERATION


def test_non_compound_query_takes_the_unchanged_single_answer_path(stub_generator) -> None:
    """A single sub-question never fans out (_run_retrieval only fans out for
    len(sub_questions) > 1) — sub_answers stays empty, exactly as before item 3."""
    def _retrieve(q, **_k):
        return _retrieval([_chunk("only-doc", 0)], query=q)

    st = _state([SubQuestion(text="compound q")], _retrieve)
    _run_through_generation(st)

    assert st.sub_retrievals == []
    assert st.sub_answers == []
    assert st.abstained is False
    assert st.generation_ref is not None
