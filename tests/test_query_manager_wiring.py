"""
tests/test_query_manager_wiring.py — the route↔Manager seam.

``tests/test_query_answer_route.py`` covers the HTTP contract and
``tests/test_agent_manager.py`` covers the orchestration. This file covers the
join between them, which is where a behaviour-preserving port is easiest to get
subtly wrong: the plan-failure → status-code mapping, and the observer adapter
that has to reproduce the pre-Phase-2 LangSmith spans exactly.
"""

from __future__ import annotations

from typing import Any

import pytest

from api.routes import query as query_route
from rag.agents.manager import ManagerError

# ── Plan failure → status code ───────────────────────────────


@pytest.mark.parametrize(
    ("stage", "kind", "status"),
    [
        ("retrieval", "failure", 500),
        ("grounding", "empty", 422),
        ("grounding", "low_confidence", 422),
        ("generation", "config", 500),
        ("generation", "failure", 500),
    ],
)
def test_every_plan_failure_maps_to_its_original_status(
    stage: str, kind: str, status: int
) -> None:
    """The codes the route returned before the port, preserved one for one."""
    exc = ManagerError("boom", stage=stage, kind=kind)
    assert query_route._http_error(exc).status_code == status


def test_detail_is_the_manager_message_verbatim() -> None:
    """Users and tests read this string; the port must not reword it."""
    exc = ManagerError("No relevant chunks found for this query.",
                       stage="grounding", kind="empty")
    assert query_route._http_error(exc).detail == "No relevant chunks found for this query."


def test_empty_corpus_reports_the_short_form_on_the_root_span() -> None:
    """
    The root trace said "No relevant chunks found." while the caller got the
    longer sentence. A cosmetic difference, but it is pre-existing behaviour and
    a zero-change port keeps it.
    """
    exc = ManagerError("No relevant chunks found for this query.",
                       stage="grounding", kind="empty")
    assert query_route._root_trace_error(exc) == "No relevant chunks found."


def test_other_failures_put_the_full_message_on_the_root_span() -> None:
    """Everything except the empty case reports str(exc)."""
    exc = ManagerError("Retrieval error: pgvector down",
                       stage="retrieval", kind="failure")
    assert query_route._root_trace_error(exc) == "Retrieval error: pgvector down"


# ── Injected dependencies ────────────────────────────────────


def test_deps_inject_this_modules_retrieval_and_thresholds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The thresholds are read at call time from this module.

    tests/test_sprint8.py patches ``api.routes.query.MIN_GROUNDED_CHUNKS``; if
    the Manager imported the guard's knobs itself, that patch would stop biting
    and the grounding tests would quietly stop testing anything.
    """
    monkeypatch.setattr(query_route, "MIN_GROUNDED_CHUNKS", 7)
    monkeypatch.setattr(query_route, "MIN_GROUNDED_TOP_SIM", 0.91)
    deps = query_route._build_manager_deps(None)

    assert deps.min_chunks == 7
    assert deps.min_top_sim == 0.91
    assert deps.retrieve is query_route.retrieve_with_project


# ── The LangSmith observer adapter ───────────────────────────


class _SpanRecorder:
    """Stands in for _start_trace / _end_trace."""

    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.ended: list[tuple[Any, Any, Any]] = []

    def start(self, **kwargs: Any) -> str:
        self.started.append(kwargs)
        return f"span-{len(self.started)}"

    def end(self, run: Any, outputs: Any = None, error: Any = None) -> None:
        self.ended.append((run, outputs, error))


@pytest.fixture()
def spans(monkeypatch: pytest.MonkeyPatch) -> _SpanRecorder:
    """Swap the module's LangSmith helpers for a recorder."""
    recorder = _SpanRecorder()
    monkeypatch.setattr(query_route, "_start_trace", recorder.start)
    monkeypatch.setattr(query_route, "_end_trace", recorder.end)
    return recorder


def _observer() -> Any:
    """An observer parented to a sentinel root span."""
    return query_route._LangSmithObserver("ROOT", session_id="s1", request_id="r1")


def test_retrieval_span_keeps_its_name_type_and_parent(spans: _SpanRecorder) -> None:
    """api_retrieval, run_type=tool, child of the root — unchanged from before."""
    _observer().started("retrieval", {"query": "q", "top_k": 5})
    span = spans.started[0]

    assert span["name"] == "api_retrieval"
    assert span["run_type"] == "tool"
    assert span["parent"] == "ROOT"
    assert span["extra"] is None


def test_generation_span_carries_identity_and_prompt_version(
    spans: _SpanRecorder,
) -> None:
    """The generation span always tagged session, request, and prompt version."""
    _observer().started("generation", {"query": "q", "num_chunks": 3})
    span = spans.started[0]

    assert span["name"] == "api_generation"
    assert span["run_type"] == "llm"
    assert span["inputs"]["session_id"] == "s1"
    assert span["inputs"]["request_id"] == "r1"
    assert span["inputs"]["num_chunks"] == 3
    assert span["extra"] == {"metadata": {"prompt_version": query_route.PROMPT_VERSION}}


def test_observer_does_not_mutate_the_managers_inputs(spans: _SpanRecorder) -> None:
    """The adapter's additions must not leak back into the Manager's dict."""
    inputs = {"query": "q"}
    _observer().started("generation", inputs)
    assert inputs == {"query": "q"}


def test_finished_closes_the_matching_span(spans: _SpanRecorder) -> None:
    """Outputs land on the span that was opened for that stage."""
    observer = _observer()
    observer.started("retrieval", {"query": "q"})
    observer.finished("retrieval", {"num_results": 3})

    assert spans.ended == [("span-1", {"num_results": 3}, None)]


def test_failed_closes_the_span_with_an_error(spans: _SpanRecorder) -> None:
    """A failing stage must not leave its span open."""
    observer = _observer()
    observer.started("generation", {"query": "q"})
    observer.failed("generation", "Generation error: boom")

    assert spans.ended == [("span-1", None, "Generation error: boom")]


def test_stages_close_independently(spans: _SpanRecorder) -> None:
    """Retrieval closing must not close generation's span, or vice versa."""
    observer = _observer()
    observer.started("retrieval", {"query": "q"})
    observer.started("generation", {"query": "q"})
    observer.finished("generation", {"model": "m"})
    observer.finished("retrieval", {"num_results": 3})

    assert [run for run, _o, _e in spans.ended] == ["span-2", "span-1"]


def test_closing_an_unopened_stage_is_a_no_op(spans: _SpanRecorder) -> None:
    """Defensive: a mismatched callback closes nothing rather than raising."""
    _observer().finished("retrieval", {"num_results": 0})
    assert spans.ended == [(None, {"num_results": 0}, None)]
