"""
tests/test_audit_logger.py — trace store writer.

Covers the three things Phase 0 has to get right: cost math (including cache
tiers and time-boxed intro pricing), usage extraction across the three result
shapes in this codebase, and the guarantee that tracing never raises into the
request it is observing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

import pytest

from audit import logger as audit_logger
from audit.logger import (
    StepUsage,
    input_hash,
    model_from,
    record_step,
    resolve_pricing,
    start_run,
    traced,
    usage_from,
)

# ── Fakes matching the three shapes in this codebase ─────────


@dataclass
class _FakeUsage:
    """The Anthropic response.usage shape."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class _FakeResponse:
    """An Anthropic response object."""

    usage: _FakeUsage
    model: str = "claude-haiku-4-5-20251001"


@dataclass
class _FakeGenerationResult:
    """The rag.generator.GenerationResult shape — counts are top level."""

    model: str = "claude-sonnet-5"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class _RecordingClient:
    """Stand-in for db.client that captures writes instead of issuing SQL."""

    def __init__(self) -> None:
        self.runs: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []
        self.finished: list[dict[str, Any]] = []

    def insert_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": uuid4(), **kwargs}
        self.runs.append(row)
        return row

    def insert_agent_step(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": uuid4(), **kwargs}
        self.steps.append(row)
        return row

    def finish_agent_run(self, run_id: Any, **kwargs: Any) -> dict[str, Any]:
        row = {"id": run_id, **kwargs}
        self.finished.append(row)
        return row

    def annotate_agent_run(self, run_id: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": run_id, **kwargs}


@pytest.fixture()
def fake_db(monkeypatch: pytest.MonkeyPatch) -> _RecordingClient:
    """Swap the db client for a recorder."""
    client = _RecordingClient()
    monkeypatch.setattr(audit_logger, "db_client", client)
    return client


# ── Pricing ──────────────────────────────────────────────────


def test_dated_model_ids_resolve_to_their_base_rate() -> None:
    """LLM_MODEL defaults to a dated id; it must price like the base model."""
    assert resolve_pricing("claude-haiku-4-5-20251001") == (1.00, 5.00)


def test_sonnet_5_intro_pricing_expires_on_schedule() -> None:
    """Intro pricing applies through 2026-08-31, list price after."""
    assert resolve_pricing("claude-sonnet-5", on=date(2026, 8, 31)) == (2.00, 10.00)
    assert resolve_pricing("claude-sonnet-5", on=date(2026, 9, 1)) == (3.00, 15.00)


def test_unknown_models_price_at_zero_rather_than_raising() -> None:
    """A local Ollama runtime must not take down the request path."""
    assert resolve_pricing("qwen2.5:14b-instruct-q4_K_M") == (0.0, 0.0)
    assert resolve_pricing(None) == (0.0, 0.0)


def test_cost_uses_cache_tiers() -> None:
    """Cache reads bill at 0.1x input; writes at 1.25x (5m) or 2.0x (1h)."""
    usage = StepUsage(tokens_in=0, tokens_out=0, cache_read=1_000_000)
    assert usage.cost_usd("claude-opus-4-8") == pytest.approx(0.50)

    write = StepUsage(cache_write=1_000_000)
    assert write.cost_usd("claude-opus-4-8") == pytest.approx(6.25)
    assert write.cost_usd("claude-opus-4-8", cache_ttl_1h=True) == pytest.approx(10.00)


def test_cost_matches_hand_computed_baseline() -> None:
    """The plan's baseline query: 4,730 in + 400 out on haiku."""
    usage = StepUsage(tokens_in=4_730, tokens_out=400)
    assert usage.cost_usd("claude-haiku-4-5") == pytest.approx(0.00673, abs=1e-5)


# ── Usage extraction ─────────────────────────────────────────


def test_usage_from_anthropic_response() -> None:
    """The provider shape, where counts hang off .usage."""
    response = _FakeResponse(
        usage=_FakeUsage(
            input_tokens=100,
            output_tokens=50,
            cache_read_input_tokens=20,
            cache_creation_input_tokens=10,
        )
    )
    usage = usage_from(response)
    assert (usage.tokens_in, usage.tokens_out) == (100, 50)
    assert (usage.cache_read, usage.cache_write) == (20, 10)


def test_usage_from_generation_result() -> None:
    """The dataclass shape, where counts are top level."""
    usage = usage_from(
        _FakeGenerationResult(
            input_tokens=4_730, output_tokens=1_500, cache_read_input_tokens=4_000
        )
    )
    assert usage.tokens_in == 4_730
    assert usage.cache_read == 4_000


def test_usage_from_nested_dict() -> None:
    """rag/design_intent.py returns a dict with a nested usage key."""
    result = {
        "overlays": [],
        "usage": {"input_tokens": 300, "output_tokens": 120, "model": "claude-haiku-4-5"},
    }
    usage = usage_from(result)
    assert (usage.tokens_in, usage.tokens_out) == (300, 120)
    assert model_from(result) == "claude-haiku-4-5"


def test_usage_from_unrecognised_object_yields_zeros() -> None:
    """A tracing helper must never raise on an unexpected return value."""
    assert usage_from(object()) == StepUsage()
    assert usage_from(None) == StepUsage()
    assert model_from(None) is None


# ── Input hashing ────────────────────────────────────────────


def test_input_hash_is_order_stable_for_dicts() -> None:
    """Unsorted dicts must not scatter one Crystallizer cluster."""
    assert input_hash({"b": 2, "a": 1}) == input_hash({"a": 1, "b": 2})


def test_input_hash_distinguishes_different_inputs() -> None:
    """Different logical inputs must land in different clusters."""
    assert input_hash("fence setback") != input_hash("fence height")


# ── Run and step lifecycle ───────────────────────────────────


def test_run_records_steps_and_closes_successfully(fake_db: _RecordingClient) -> None:
    """A completed run writes one row and closes with outcome=success."""
    with start_run("query_answer", intent="compliance_lookup"):
        record_step("retrieval", deterministic=True)
        record_step(
            "answer_generator",
            model="claude-haiku-4-5",
            usage=StepUsage(tokens_in=1_000, tokens_out=200),
        )

    assert len(fake_db.runs) == 1
    assert len(fake_db.steps) == 2
    assert fake_db.finished[0]["outcome"] == "success"

    deterministic_step, model_step = fake_db.steps
    assert deterministic_step["deterministic"] is True
    assert deterministic_step["cost_usd"] == 0
    assert model_step["cost_usd"] > 0
    assert [s["step_index"] for s in fake_db.steps] == [1, 2]


def test_failed_run_is_closed_with_the_error(fake_db: _RecordingClient) -> None:
    """An exception marks the run errored and still propagates."""
    with pytest.raises(ValueError, match="boom"), start_run("query_answer"):
        raise ValueError("boom")

    assert fake_db.finished[0]["outcome"] == "error"
    assert "boom" in fake_db.finished[0]["error"]


def test_steps_outside_a_run_are_dropped_silently(fake_db: _RecordingClient) -> None:
    """Untraced call paths must not error -- they simply record nothing."""
    assert record_step("orphan") is None
    assert fake_db.steps == []


def test_traced_decorator_records_model_and_usage(fake_db: _RecordingClient) -> None:
    """The decorator reads usage off the return value."""

    @traced("answer_generator", prompt_version="v1")
    def generate() -> _FakeGenerationResult:
        return _FakeGenerationResult(input_tokens=4_730, output_tokens=1_500)

    with start_run("query_answer"):
        generate()

    step = fake_db.steps[0]
    assert step["agent_name"] == "answer_generator"
    assert step["model"] == "claude-sonnet-5"
    assert step["tokens_in"] == 4_730
    assert step["prompt_version"] == "v1"
    assert step["status"] == "ok"


def test_traced_decorator_records_errors_then_reraises(fake_db: _RecordingClient) -> None:
    """A failing agent is recorded as an errored step, exception untouched."""

    @traced("answer_generator")
    def explode() -> None:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    with start_run("query_answer"), pytest.raises(RuntimeError, match="API_KEY"):
        explode()

    assert fake_db.steps[0]["status"] == "error"
    assert "ANTHROPIC_API_KEY" in fake_db.steps[0]["error"]


# ── The guarantee that matters most ──────────────────────────


def test_tracing_failure_does_not_break_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A dead database must degrade tracing to a log line, not a 500.

    This is the module's central design rule: observability is not business
    logic. Simulates migration 026 not being applied yet.
    """

    class _BrokenClient:
        def insert_agent_run(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError('relation "agent_runs" does not exist')

        def insert_agent_step(self, **_: Any) -> dict[str, Any]:
            raise RuntimeError('relation "agent_steps" does not exist')

        def finish_agent_run(self, *_: Any, **__: Any) -> dict[str, Any]:
            raise RuntimeError("connection pool is closed")

    monkeypatch.setattr(audit_logger, "db_client", _BrokenClient())

    @traced("answer_generator")
    def do_work() -> str:
        return "the answer"

    with start_run("query_answer") as ctx:
        assert ctx.enabled is False
        assert do_work() == "the answer"
