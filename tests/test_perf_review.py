"""
tests/test_perf_review.py — Performance Review (agent #24)
=========================================================
Attribution of a thumbs-down to an agent. Deterministic classes need no model;
the quality-judgement path is exercised with a mocked ``run_agent``. No DB, no
network — db reads/writes are monkeypatched.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from evaluation import perf_review
from evaluation.perf_review import Attribution


def _run(**over) -> dict:
    base = {
        "id": uuid4(),
        "outcome": "success",
        "intent": "compliance_lookup",
        "persona": "research",
        "entrypoint": "query_answer",
        "error": None,
    }
    base.update(over)
    return base


def _step(agent, **over) -> dict:
    base = {
        "step_index": 0,
        "agent_name": agent,
        "model": "claude-haiku-4-5",
        "status": "ok",
        "tokens_out": 100,
        "prompt_fragment_ids": [],
        "error": None,
    }
    base.update(over)
    return base


def test_errored_step_is_deterministic_no_llm(monkeypatch) -> None:
    """A step with status=error is attributed without calling the model."""
    run = _run(outcome="error")
    steps = [_step("retriever"), _step("answer_generator", status="error", error="boom", step_index=1)]

    def _boom(*_a, **_k):
        raise AssertionError("run_agent must not be called for an errored step")

    monkeypatch.setattr(perf_review, "run_agent", _boom)
    attr = perf_review.attribute(run, steps, use_llm=True)
    assert attr.attributed_agent == "answer_generator"
    assert attr.failure_mode == "step_error"
    assert attr.confidence >= 0.85


def test_abstain_attributed_to_retriever() -> None:
    """A grounding abstain (model='abstained') blames retrieval coverage."""
    run = _run(outcome="blocked")
    steps = [_step("retriever"), _step("manager", model="abstained", step_index=1)]
    attr = perf_review.attribute(run, steps, use_llm=False)
    assert attr.attributed_agent == "retriever"
    assert attr.failure_mode == "grounding_abstain"


def test_no_llm_leaves_unattributed() -> None:
    """With --no-llm and no deterministic verdict, blame is left to a human."""
    run = _run()
    steps = [_step("retriever"), _step("answer_generator", step_index=1)]
    attr = perf_review.attribute(run, steps, use_llm=False)
    assert attr.attributed_agent is None
    assert attr.confidence == 0.0


def test_llm_path_clamps_unknown_agent(monkeypatch) -> None:
    """A hallucinated agent name is clamped back to None (metric stays honest)."""
    run = _run()
    steps = [_step("retriever"), _step("answer_generator", step_index=1)]
    fake = Attribution(
        attributed_agent="wizard",  # not in KNOWN_AGENTS
        failure_mode="hallucination",
        evidence="made up",
        confidence=0.9,
        rationale="n/a",
    )
    monkeypatch.setattr(perf_review, "run_agent", lambda *a, **k: SimpleNamespace(parsed_output=fake))
    attr = perf_review.attribute(run, steps, use_llm=True)
    assert attr.attributed_agent is None


def test_review_run_writes_unconfirmed_correction(monkeypatch) -> None:
    """A confident review writes one unconfirmed, attributed correction."""
    run_id = uuid4()
    run = _run(id=run_id)
    captured = {}
    monkeypatch.setattr(perf_review.db_client, "get_agent_run", lambda rid: run)
    monkeypatch.setattr(perf_review.db_client, "list_agent_steps", lambda rid: [_step("retriever")])

    def _fake_insert(**kwargs):
        captured.update(kwargs)
        return {"id": uuid4()}

    monkeypatch.setattr(perf_review.db_client, "insert_agent_correction", _fake_insert)
    fake = Attribution(
        attributed_agent="answer_generator",
        failure_mode="hallucination",
        evidence="cited a chunk it did not retrieve",
        confidence=0.82,
        rationale="claim not grounded",
    )
    monkeypatch.setattr(perf_review, "run_agent", lambda *a, **k: SimpleNamespace(parsed_output=fake))

    summary = perf_review.review_run(run_id, comment="wrong setback")
    assert summary["attributed_agent"] == "answer_generator"
    assert summary["needs_human_attribution"] is False
    assert captured["source"] == "answer"
    assert captured["confirmed"] is False           # never silent blame
    assert captured["attributed_agent"] == "answer_generator"
    assert "user: wrong setback" in captured["notes"]


def test_review_run_low_confidence_drops_attribution(monkeypatch) -> None:
    """Below the floor, the row is written but carries no attributed_agent."""
    run_id = uuid4()
    monkeypatch.setattr(perf_review.db_client, "get_agent_run", lambda rid: _run(id=run_id))
    monkeypatch.setattr(perf_review.db_client, "list_agent_steps", lambda rid: [_step("retriever")])
    captured = {}
    monkeypatch.setattr(
        perf_review.db_client, "insert_agent_correction",
        lambda **k: captured.update(k) or {"id": uuid4()},
    )
    fake = Attribution(
        attributed_agent="answer_generator",
        failure_mode="unclear",
        evidence="weak",
        confidence=0.3,  # below CONFIDENCE_FLOOR
        rationale="not sure",
    )
    monkeypatch.setattr(perf_review, "run_agent", lambda *a, **k: SimpleNamespace(parsed_output=fake))

    summary = perf_review.review_run(run_id)
    assert summary["needs_human_attribution"] is True
    assert summary["attributed_agent"] is None
    assert captured["attributed_agent"] is None      # human assigns blame


def test_review_run_missing_run_returns_none(monkeypatch) -> None:
    """An unknown run id yields None (nothing to review)."""
    monkeypatch.setattr(perf_review.db_client, "get_agent_run", lambda rid: None)
    assert perf_review.review_run(uuid4()) is None
