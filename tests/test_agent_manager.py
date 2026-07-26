"""
tests/test_agent_manager.py — the Manager, and the port it must not change.

``tests/test_query_answer_route.py`` proves the HTTP contract is unchanged. This
file proves the orchestration underneath it: plan order, the ReAct bound, the
failure taxonomy the route maps to status codes, the non-blocking steps that
must degrade rather than raise, and — the property the artifact store exists for
— that the Manager's own state never contains chunk text.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from rag.agents import registry
from rag.agents.manager import (
    MAX_ITERATIONS,
    ManagerDeps,
    ManagerError,
    ManagerRequest,
    run_query_plan,
)
from rag.agents.registry import AgentSpec

_CHUNK_TEXT = "SETBACK-TEXT-THAT-MUST-NOT-REACH-THE-MANAGER"


def _chunk(doc_id: str, index: int, *, filtered_out: bool = False, tier: int = 1) -> dict:
    """A retrieval row shaped like rag.retriever output."""
    return {
        "id": uuid4(), "document_id": uuid4(), "doc_id": doc_id,
        "chunk_index": index, "content": f"{_CHUNK_TEXT}-{doc_id}",
        "municipality": "dallas", "authority_level": "municipal",
        "doc_type": "building_code", "document_status": "active",
        "source_tier": tier, "similarity": 0.88, "raw_similarity": 0.88,
        "reranked_score": 0.88, "provenance_weight": 1.0,
        "filtered_out": filtered_out,
    }


def _retrieval(chunks: list[dict] | None = None) -> SimpleNamespace:
    """A RetrievalResult stand-in, including the passing_chunks property."""
    rows = chunks if chunks is not None else [
        _chunk("dallas-building", 0), _chunk("dallas-electrical", 1),
        _chunk("dallas-plumbing", 2),
    ]
    return SimpleNamespace(
        query="q", top_k=5, municipality="dallas", chunks=rows,
        passing_chunks=[c for c in rows if not c["filtered_out"]],
        num_results=len(rows), top_similarity=0.88, mean_similarity=0.85,
        unique_documents=sorted({c["doc_id"] for c in rows}), latency_ms=25,
    )


def _generation(chunks: list[dict]) -> SimpleNamespace:
    """A GenerationResult stand-in."""
    return SimpleNamespace(
        answer="Permits required. [dallas-building, chunk 0]",
        citations=[{"doc_id": "dallas-building", "chunk_index": 0,
                    "found_in_context": True, "municipality": "dallas",
                    "authority_level": "municipal"}],
        model="claude-test", input_tokens=100, output_tokens=50,
        latency_ms=40, chunk_count=len(chunks),
    )


class _Calls:
    """Records what each stubbed agent was handed."""

    def __init__(self) -> None:
        self.order: list[str] = []
        self.generated_chunks: list[dict] = []
        self.project_context: Any = None


@pytest.fixture()
def stubs(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """
    Replace every registered agent the Manager delegates to.

    Swapping specs rather than patching modules is the honest test of the
    registry indirection: if the Manager stopped routing through it, these
    stubs would never be called.
    """
    calls = _Calls()
    saved = {name: registry.get_or_none(name) for name in (
        "permit_classifier", "jurisdiction_resolver", "conflict_detector",
        "mini_rag_conflicts", "project_context", "answer_generator",
    )}

    def _generate(query: str, chunks: list[dict], **kwargs: Any) -> Any:
        calls.order.append("answer_generator")
        calls.generated_chunks = chunks
        calls.project_context = kwargs.get("project_context")
        return _generation(chunks)

    def _spec(name: str, fn: Any) -> None:
        registry.register(AgentSpec(name=name, callable=fn), replace=True)

    _spec("permit_classifier", lambda q: calls.order.append("permit_classifier") or ["building"])
    _spec("jurisdiction_resolver", lambda a: calls.order.append("jurisdiction_resolver") or "plano")
    _spec("conflict_detector", lambda c: calls.order.append("conflict_detector") or [])
    _spec("mini_rag_conflicts", lambda a, b: calls.order.append("mini_rag_conflicts") or [])
    _spec("project_context", lambda p: calls.order.append("project_context") or {"persona": "diy"})
    _spec("answer_generator", _generate)

    yield calls

    for spec in saved.values():
        if spec is not None:
            registry.register(spec, replace=True)


def _deps(result: Any = None, **overrides: Any) -> ManagerDeps:
    """Build deps whose retrieval returns ``result`` and records the call."""
    payload = _retrieval() if result is None else result
    return ManagerDeps(retrieve=lambda *_a, **_k: payload, min_chunks=1,
                       min_top_sim=0.0, **overrides)


# ── Plan shape ───────────────────────────────────────────────


def test_plan_runs_every_step_in_order(stubs: _Calls) -> None:
    """Project context loads first (wave 1) so retrieval + jurisdiction + routing
    are project-aware from a project_id alone; the rest of the order is preserved."""
    run_query_plan(
        ManagerRequest(query="q", address="1 Main St", project_id=str(uuid4())), _deps()
    )
    assert stubs.order == [
        "project_context", "permit_classifier", "jurisdiction_resolver",
        "conflict_detector", "mini_rag_conflicts", "answer_generator",
    ]


def test_plan_stays_within_the_react_bound(stubs: _Calls) -> None:
    """A growing transcript is the ReAct cost multiplier; the bound is the guard."""
    result = run_query_plan(ManagerRequest(query="q"), _deps())
    assert 0 < result.iterations <= MAX_ITERATIONS


def test_project_only_steps_are_skipped_without_a_project(stubs: _Calls) -> None:
    """No project id, no upload-conflict check and no project context load."""
    run_query_plan(ManagerRequest(query="q"), _deps())
    assert "mini_rag_conflicts" not in stubs.order
    assert "project_context" not in stubs.order


def test_project_context_reaches_the_generator(stubs: _Calls) -> None:
    """Loaded facts are handed on, not merely stored."""
    run_query_plan(ManagerRequest(query="q", project_id=str(uuid4())), _deps())
    assert stubs.project_context == {"persona": "diy"}


# ── The reason the artifact store exists ─────────────────────


def test_the_manager_never_holds_chunk_text(stubs: _Calls) -> None:
    """
    Summaries the Manager reasons over must not contain the payload.

    This is what bounds ReAct's blast radius — and what makes it impossible for
    the Manager to leak superseded text into a prompt.
    """
    result = run_query_plan(ManagerRequest(query="q"), _deps())
    blob = " ".join(ref.describe() for ref in result.artifacts)

    assert _CHUNK_TEXT not in blob
    assert "chunks" in {ref.kind for ref in result.artifacts}
    assert "answer" in {ref.kind for ref in result.artifacts}


def test_artifacts_still_resolve_to_the_real_payloads(stubs: _Calls) -> None:
    """Refs bound the loop; the caller still gets the objects it needs."""
    result = run_query_plan(ManagerRequest(query="q"), _deps())
    assert result.retrieval.num_results == 3
    assert result.generation.model == "claude-test"


# ── Chunk filtering (Phase 0 defect #2, preserved) ───────────


def test_only_reranker_passing_chunks_reach_the_generator(stubs: _Calls) -> None:
    """Rejected chunks must not be prompted or billed."""
    rows = [_chunk("keep", 0), _chunk("keep-2", 1),
            _chunk("rejected", 2, filtered_out=True), _chunk("keep-3", 3)]
    run_query_plan(ManagerRequest(query="q"), _deps(_retrieval(rows)))
    assert [c["doc_id"] for c in stubs.generated_chunks] == ["keep", "keep-2", "keep-3"]


# ── Failure taxonomy the route maps to status codes ──────────


def test_retrieval_failure_is_a_500_shaped_error(stubs: _Calls) -> None:
    """stage=retrieval → the route's 500, with the message text preserved."""
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ConnectionError("pgvector down")

    with pytest.raises(ManagerError) as caught:
        run_query_plan(ManagerRequest(query="q"), ManagerDeps(retrieve=_boom))
    assert caught.value.stage == "retrieval"
    assert str(caught.value).startswith("Retrieval error: ")


def test_empty_retrieval_abstains_not_raises(stubs: _Calls) -> None:
    """Phase 4 query-UX: no chunks is a soft abstain (200), not a raise (422)."""
    result = run_query_plan(ManagerRequest(query="q"), _deps(_retrieval([])))
    assert result.abstained is True
    assert result.generation is None           # generation skipped
    assert result.abstain_message              # a user-facing message is set
    assert "answer_generator" not in stubs.order  # the model was never called


def test_low_confidence_abstains_not_raises(stubs: _Calls) -> None:
    """A below-floor top_similarity abstains rather than raising a grounding 422."""
    deps = ManagerDeps(retrieve=lambda *_a, **_k: _retrieval(),
                       min_chunks=3, min_top_sim=0.99)
    result = run_query_plan(ManagerRequest(query="q"), deps)
    assert result.abstained is True
    assert result.generation is None
    assert "answer_generator" not in stubs.order


def test_generator_config_error_is_distinguishable(stubs: _Calls) -> None:
    """A missing API key is kind=config, so the route can pass str(exc) through."""
    def _no_key(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    registry.register(AgentSpec(name="answer_generator", callable=_no_key), replace=True)
    with pytest.raises(ManagerError) as caught:
        run_query_plan(ManagerRequest(query="q"), _deps())
    assert (caught.value.stage, caught.value.kind) == ("generation", "config")
    assert str(caught.value) == "ANTHROPIC_API_KEY is not set."


# ── Non-blocking steps degrade, never raise ──────────────────


@pytest.mark.parametrize(
    "agent", ["permit_classifier", "jurisdiction_resolver", "conflict_detector",
              "mini_rag_conflicts", "project_context"],
)
def test_enrichment_failures_never_break_the_answer(stubs: _Calls, agent: str) -> None:
    """Every pre/post-retrieval step is advisory; only the answer path is fatal."""
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError(f"{agent} exploded")

    registry.register(AgentSpec(name=agent, callable=_boom), replace=True)
    result = run_query_plan(
        ManagerRequest(query="q", address="1 Main St", project_id=str(uuid4())), _deps()
    )
    assert result.generation.model == "claude-test"


def test_classifier_failure_yields_an_empty_permit_type_list(stubs: _Calls) -> None:
    """Matches the route's documented fallback."""
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("classifier boom")

    registry.register(AgentSpec(name="permit_classifier", callable=_boom), replace=True)
    assert run_query_plan(ManagerRequest(query="q"), _deps()).permit_types == []


# ── Jurisdiction resolution ──────────────────────────────────


def test_address_geocoding_fills_the_effective_municipality(stubs: _Calls) -> None:
    """An unspecified municipality is resolved from the address and reported."""
    result = run_query_plan(ManagerRequest(query="q", address="1 Main St"), _deps())
    assert result.resolved_municipality == "plano"
    assert result.effective_municipality == "plano"


def test_project_municipality_used_when_request_omits_it(stubs: _Calls) -> None:
    """A project's stored municipality scopes the query from a project_id alone."""
    registry.register(
        AgentSpec(
            name="project_context",
            callable=lambda p: {"persona": "diy", "municipality": "frisco"},
        ),
        replace=True,
    )
    result = run_query_plan(
        ManagerRequest(query="q", project_id=str(uuid4())), _deps()
    )
    assert result.effective_municipality == "frisco"


# ── Media Curator (agent #17) — diy path only ────────────────

_MEDIA_ROW = {
    "task_key": "install_gfci_outlet", "title": "GFCI how-to",
    "url": "https://www.youtube.com/watch?v=abc", "provider": "youtube",
    "jurisdiction": None, "relevance_note": "step by step", "last_verified_at": None,
}


def test_diy_query_surfaces_sourced_media(
    stubs: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diy persona + a curated task yields vetted videos on the result."""
    import db.client as db_client
    monkeypatch.setattr(db_client, "fetch_media_refs", lambda *_a, **_k: [_MEDIA_ROW])
    # default stub project_context → persona 'diy'
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        _deps(),
    )
    assert [m.url for m in result.media_refs] == ["https://www.youtube.com/watch?v=abc"]
    assert all(m.sourced for m in result.media_refs)  # zero unsourced URLs


def test_non_diy_persona_gets_no_media(
    stubs: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    import db.client as db_client
    monkeypatch.setattr(db_client, "fetch_media_refs", lambda *_a, **_k: [_MEDIA_ROW])
    registry.register(
        AgentSpec(name="project_context", callable=lambda p: {"persona": "contractor"}),
        replace=True,
    )
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        _deps(),
    )
    assert result.media_refs == []


def test_diy_abstain_still_surfaces_media(
    stubs: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diy abstain has no answer, but the curated how-to links still show."""
    import db.client as db_client
    monkeypatch.setattr(db_client, "fetch_media_refs", lambda *_a, **_k: [_MEDIA_ROW])
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        _deps(_retrieval([])),  # empty retrieval → abstain
    )
    assert result.abstained is True
    assert [m.url for m in result.media_refs] == ["https://www.youtube.com/watch?v=abc"]


def test_non_diy_abstain_has_no_media(
    stubs: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-diy abstain surfaces neither an answer nor videos."""
    import db.client as db_client
    monkeypatch.setattr(db_client, "fetch_media_refs", lambda *_a, **_k: [_MEDIA_ROW])
    registry.register(
        AgentSpec(name="project_context", callable=lambda p: {"persona": "research"}),
        replace=True,
    )
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        _deps(_retrieval([])),
    )
    assert result.abstained is True
    assert result.media_refs == []


# ── How-to fallback (Media Curator Slice C2) ─────────────────


def _how_to_deps(*, compliance: Any, how_to: Any, **overrides: Any) -> ManagerDeps:
    """Deps whose compliance + how-to retrievals return the given results."""
    return ManagerDeps(
        retrieve=lambda *_a, **_k: compliance,
        min_chunks=1, min_top_sim=0.0,
        retrieve_how_to=lambda *_a, **_k: how_to,
        **overrides,
    )


def test_diy_abstain_answered_from_how_to(
    stubs: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A diy compliance-abstain becomes a grounded how-to answer when transcripts hit."""
    import db.client as db_client
    monkeypatch.setattr(db_client, "fetch_media_refs", lambda *_a, **_k: [_MEDIA_ROW])
    # compliance empty → abstain; how-to retrieval grounds (top_sim 0.88 > 0.50 floor)
    deps = _how_to_deps(compliance=_retrieval([]), how_to=_retrieval())
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        deps,
    )
    assert result.abstained is False          # the how-to answer replaced the abstain
    assert result.how_to is True
    assert result.generation.model == "claude-test"
    assert [m.url for m in result.media_refs] == ["https://www.youtube.com/watch?v=abc"]


def test_how_to_below_floor_stays_abstained(stubs: _Calls) -> None:
    """No how-to chunk clears the floor → the plain abstain stands."""
    deps = _how_to_deps(compliance=_retrieval([]), how_to=_retrieval([]))
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        deps,
    )
    assert result.abstained is True
    assert result.how_to is False


def test_non_diy_abstain_never_tries_how_to(stubs: _Calls) -> None:
    """The how-to fallback is diy-only, even when transcripts would ground."""
    registry.register(
        AgentSpec(name="project_context", callable=lambda p: {"persona": "research"}),
        replace=True,
    )
    called = {"how_to": False}

    def _how_to_retrieve(*_a: Any, **_k: Any) -> Any:
        called["how_to"] = True
        return _retrieval()

    deps = ManagerDeps(
        retrieve=lambda *_a, **_k: _retrieval([]), min_chunks=1, min_top_sim=0.0,
        retrieve_how_to=_how_to_retrieve,
    )
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        deps,
    )
    assert result.abstained is True
    assert result.how_to is False
    assert called["how_to"] is False          # never even attempted for non-diy


def test_diy_compliance_answer_is_not_overridden(stubs: _Calls) -> None:
    """A diy query that DOES get a compliance answer is not replaced by how-to.

    (The how-to retrieval may still run for semantic *links* — what must not
    happen is a how-to *answer* replacing the grounded compliance one.)"""
    deps = ManagerDeps(
        retrieve=lambda *_a, **_k: _retrieval(), min_chunks=1, min_top_sim=0.0,
        retrieve_how_to=lambda *_a, **_k: _retrieval([]),  # no how-to chunks
    )
    result = run_query_plan(
        ManagerRequest(query="how do I install a gfci outlet", project_id=str(uuid4())),
        deps,
    )
    assert result.abstained is False
    assert result.how_to is False             # compliance answer stands, not overridden


def test_semantic_links_surface_video_without_task_key(
    stubs: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A video with no curated task_key surfaces as a link via a semantic
    transcript hit (the scaling unlock for channel ingest)."""
    import db.client as db_client
    monkeypatch.setattr(db_client, "fetch_media_refs", lambda *_a, **_k: [])  # no task_key match
    row = {
        "doc_id": "how-to-abc", "task_key": "", "title": "GFCI how-to",
        "url": "https://www.youtube.com/watch?v=abc", "provider": "youtube",
        "jurisdiction": None, "relevance_note": None, "last_verified_at": None,
    }
    monkeypatch.setattr(
        db_client, "fetch_media_refs_for_how_to_docs",
        lambda ids: [row] if "how-to-abc" in ids else [],
    )
    deps = ManagerDeps(
        retrieve=lambda *_a, **_k: _retrieval(), min_chunks=1, min_top_sim=0.0,
        retrieve_how_to=lambda *_a, **_k: _retrieval([_chunk("how-to-abc", 0)]),
    )
    result = run_query_plan(
        ManagerRequest(query="how do I frobnicate a widget", project_id=str(uuid4())),
        deps,
    )
    assert [m.url for m in result.media_refs] == ["https://www.youtube.com/watch?v=abc"]


def test_explicit_municipality_is_never_overridden(stubs: _Calls) -> None:
    """The user's choice wins; the geocoder is not even consulted."""
    result = run_query_plan(
        ManagerRequest(query="q", municipality="dallas", address="1 Main St"), _deps()
    )
    assert result.resolved_municipality is None
    assert result.effective_municipality == "dallas"
    assert "jurisdiction_resolver" not in stubs.order


# ── Observer spans ───────────────────────────────────────────


class _RecordingObserver:
    """Captures the stage callbacks the route turns into LangSmith spans."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def started(self, stage: str, inputs: dict) -> None:
        self.events.append(("started", stage))

    def finished(self, stage: str, outputs: dict) -> None:
        self.events.append(("finished", stage))

    def failed(self, stage: str, error: str) -> None:
        self.events.append(("failed", stage))


def test_observer_sees_both_spans_open_and_close(stubs: _Calls) -> None:
    """Retrieval and generation each get a matched start/finish."""
    observer = _RecordingObserver()
    run_query_plan(ManagerRequest(query="q"), _deps(observer=observer))
    assert observer.events == [
        ("started", "retrieval"), ("finished", "retrieval"),
        ("started", "generation"), ("finished", "generation"),
    ]


def test_observer_sees_a_failed_stage(stubs: _Calls) -> None:
    """A failing span closes with an error rather than being left open."""
    def _boom(*_a: Any, **_k: Any) -> Any:
        raise ConnectionError("down")

    observer = _RecordingObserver()
    with pytest.raises(ManagerError):
        run_query_plan(ManagerRequest(query="q"),
                       ManagerDeps(retrieve=_boom, observer=observer))
    assert ("failed", "retrieval") in observer.events


def test_a_broken_observer_never_breaks_the_plan(stubs: _Calls) -> None:
    """Observability is not business logic."""
    class _Hostile:
        def started(self, stage: str, inputs: dict) -> None:
            raise RuntimeError("observer down")

        def finished(self, stage: str, outputs: dict) -> None:
            raise RuntimeError("observer down")

        def failed(self, stage: str, error: str) -> None:
            raise RuntimeError("observer down")

    result = run_query_plan(ManagerRequest(query="q"), _deps(observer=_Hostile()))
    assert result.generation.model == "claude-test"


# ── Import boundary ──────────────────────────────────────────


def test_manager_does_not_import_commerce_forms_or_bids() -> None:
    """AGENTS.md: api/main.py injects those agents; rag/agents/ never imports them."""
    from pathlib import Path

    import rag.agents.manager as manager_module

    lines = Path(manager_module.__file__).read_text(encoding="utf-8").splitlines()
    imports = [ln.strip() for ln in lines
               if ln.strip().startswith(("import ", "from ")) and " import " in f"{ln} "]
    banned = ("commerce", "forms", "bids")
    offenders = [ln for ln in imports if any(f" {pkg}" in ln or f"{pkg}." in ln
                                             for pkg in banned)]
    assert offenders == []
