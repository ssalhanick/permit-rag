"""
tests/test_agent_runtime.py — the single Anthropic call site.

Covers the things Phase 1 has to get right without touching a real API: the
model ladder, the cache-prefix decision (the silent-no-cache footgun), autonomy
enforcement (fail-closed), token budgeting, retries, and that every call records
exactly one trace step carrying model, usage, and the resolved autonomy level.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from audit import logger as audit_logger
from rag import agent_runtime
from rag.agent_runtime import (
    AutonomyError,
    BudgetError,
    RuntimeResult,
    Tier,
    enforce_autonomy,
    min_cache_prefix,
    model_for_tier,
    resolve_autonomy_level,
    run_agent,
)

# ── Fake Anthropic client ────────────────────────────────────


@dataclass
class _FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 40
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, *, parsed: Any = None, model: str = "claude-haiku-4-5") -> None:
        self.usage = _FakeUsage()
        self.model = model
        self.content = [_FakeBlock("hello")]
        self.stop_reason = "end_turn"
        self.parsed_output = parsed


class _FakeMessages:
    def __init__(self, parent: _FakeClient) -> None:
        self._parent = parent

    def count_tokens(self, **kwargs: Any) -> Any:
        return SimpleNamespace(input_tokens=self._parent.count)

    def create(self, **kwargs: Any) -> Any:
        return self._parent._respond("create", kwargs)

    def parse(self, **kwargs: Any) -> Any:
        return self._parent._respond("parse", kwargs)


class _FakeClient:
    """Records calls; can be told to fail N times before succeeding."""

    def __init__(self, *, response: _FakeResponse, count: int = 120,
                 fail_times: int = 0, error: type[Exception] = RuntimeError) -> None:
        self.response = response
        self.count = count
        self.fail_times = fail_times
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.messages = _FakeMessages(self)

    def _respond(self, kind: str, kwargs: dict[str, Any]) -> Any:
        self.calls.append((kind, kwargs))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise self.error("transient")
        return self.response


# ── Trace recorder (doubles as the autonomy source) ──────────


class _Recorder:
    def __init__(self, autonomy: dict[tuple[str, str], dict[str, str]] | None = None) -> None:
        self.steps: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self._autonomy = autonomy or {}

    def insert_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": uuid4(), **kwargs}
        self.runs.append(row)
        return row

    def finish_agent_run(self, run_id: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": run_id, **kwargs}

    def annotate_agent_run(self, run_id: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": run_id, **kwargs}

    def insert_agent_step(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": uuid4(), **kwargs}
        self.steps.append(row)
        return row

    def get_agent_autonomy(self, agent_name: str, scope: str = "default") -> Any:
        return self._autonomy.get((agent_name, scope))


@pytest.fixture()
def wired(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """Point both the runtime and the logger at one in-memory recorder."""
    rec = _Recorder()
    monkeypatch.setattr(agent_runtime, "db_client", rec)
    monkeypatch.setattr(audit_logger, "db_client", rec)
    monkeypatch.setattr(agent_runtime.time, "sleep", lambda *_: None)
    return rec


# ── Model ladder ─────────────────────────────────────────────


def test_model_ladder() -> None:
    assert model_for_tier(Tier.CHEAP) == "claude-haiku-4-5"
    assert model_for_tier(Tier.MID) == "claude-sonnet-5"
    assert model_for_tier(Tier.TOP) == "claude-opus-4-8"


def test_min_cache_prefix_by_family() -> None:
    """4096 on Haiku/Opus, 2048 on Sonnet — the numbers the footgun turns on."""
    assert min_cache_prefix("claude-haiku-4-5") == 4096
    assert min_cache_prefix("claude-opus-4-8") == 4096
    assert min_cache_prefix("claude-sonnet-5") == 2048


# ── Autonomy (fail closed) ───────────────────────────────────


def test_unregistered_agent_defaults_to_l0(wired: _Recorder) -> None:
    """An agent absent from agent_autonomy has no authority."""
    assert resolve_autonomy_level("ghost") == "L0"


def test_current_level_clamped_to_ceiling(wired: _Recorder) -> None:
    """A stored level above the ceiling is capped on read, not trusted."""
    wired._autonomy[("bold", "default")] = {"current_level": "L3", "max_level": "L1"}
    assert resolve_autonomy_level("bold") == "L1"


def test_enforce_autonomy_blocks_below_required(wired: _Recorder) -> None:
    wired._autonomy[("filer", "submit")] = {"current_level": "L1", "max_level": "L1"}
    assert enforce_autonomy("filer", "L1", scope="submit") == "L1"
    with pytest.raises(AutonomyError):
        enforce_autonomy("filer", "L2", scope="submit")


def test_required_autonomy_blocks_the_call_before_any_api(wired: _Recorder) -> None:
    """A gated call never reaches the model when authority is insufficient."""
    client = _FakeClient(response=_FakeResponse())
    with audit_logger.start_run("t"), pytest.raises(AutonomyError):
        run_agent("ghost", system="s", messages=[{"role": "user", "content": "x"}],
                  required_autonomy="L2", client=client)
    assert client.calls == []


# ── The call, traced ─────────────────────────────────────────


def test_create_path_records_one_step_with_usage(wired: _Recorder) -> None:
    client = _FakeClient(response=_FakeResponse())
    with audit_logger.start_run("t"):
        result = run_agent("answer_generator", system="s",
                           messages=[{"role": "user", "content": "x"}],
                           tier=Tier.CHEAP, client=client)
    assert isinstance(result, RuntimeResult)
    assert result.text == "hello"
    assert len(wired.steps) == 1
    step = wired.steps[0]
    assert step["agent_name"] == "answer_generator"
    assert step["model"] == "claude-haiku-4-5"
    assert step["tokens_in"] == 120 and step["tokens_out"] == 40
    assert step["autonomy_level"] == "L0"
    assert step["cost_usd"] > 0


def test_parse_path_returns_parsed_output(wired: _Recorder) -> None:
    from pydantic import BaseModel

    class Out(BaseModel):
        value: int

    client = _FakeClient(response=_FakeResponse(parsed=Out(value=7)))
    with audit_logger.start_run("t"):
        result = run_agent("x", system="s", messages=[{"role": "user", "content": "x"}],
                           output_format=Out, client=client)
    assert client.calls[-1][0] == "parse"
    assert result.parsed_output.value == 7


# ── Caching decision ─────────────────────────────────────────


def test_no_cache_breakpoint_below_minimum_prefix(wired: _Recorder) -> None:
    """A small system prompt must be sent as a plain string (silent-no-cache)."""
    client = _FakeClient(response=_FakeResponse(), count=500)
    with audit_logger.start_run("t"):
        run_agent("x", system="short", messages=[{"role": "user", "content": "x"}],
                  cache_system=True, client=client)
    assert client.calls[-1][1]["system"] == "short"


def test_cache_breakpoint_when_prefix_clears_minimum(wired: _Recorder) -> None:
    """Above the minimum, a cache_control breakpoint is attached."""
    client = _FakeClient(response=_FakeResponse(), count=5000)
    with audit_logger.start_run("t"):
        run_agent("x", system="big", messages=[{"role": "user", "content": "x"}],
                  cache_system=True, cache_ttl_1h=True, client=client)
    system = client.calls[-1][1]["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


# ── Budget, retries, error tracing ───────────────────────────


def test_budget_exceeded_raises_before_the_call(wired: _Recorder) -> None:
    client = _FakeClient(response=_FakeResponse(), count=9000)
    with audit_logger.start_run("t"), pytest.raises(BudgetError):
        run_agent("x", system="s", messages=[{"role": "user", "content": "x"}],
                  token_budget=1000, client=client)
    assert all(k != "create" for k, _ in client.calls)


def test_transient_errors_retry_then_succeed(
    wired: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _TransientError(Exception):
        pass

    monkeypatch.setattr(agent_runtime, "_retryable_errors", lambda: (_TransientError,))
    client = _FakeClient(response=_FakeResponse(), fail_times=2, error=_TransientError)
    with audit_logger.start_run("t"):
        result = run_agent("x", system="s", messages=[{"role": "user", "content": "x"}],
                           max_retries=3, client=client)
    assert result.text == "hello"
    assert sum(1 for k, _ in client.calls if k == "create") == 3


def test_non_retryable_error_records_error_step_and_reraises(wired: _Recorder) -> None:
    client = _FakeClient(response=_FakeResponse(), fail_times=1, error=ValueError)
    with audit_logger.start_run("t"), pytest.raises(ValueError):
        run_agent("x", system="s", messages=[{"role": "user", "content": "x"}],
                  max_retries=0, client=client)
    assert wired.steps[-1]["status"] == "error"
    assert "ValueError" in wired.steps[-1]["error"]


def test_temperature_deprecated_retries_without_it(wired: _Recorder) -> None:
    """A model that 400s on `temperature` (Sonnet 5) is retried without it."""
    agent_runtime._TEMPERATURE_UNSUPPORTED.discard("claude-sonnet-5")
    seen: list[dict[str, Any]] = []

    class _Msgs:
        def count_tokens(self, **k: Any) -> Any:
            return SimpleNamespace(input_tokens=120)

        def create(self, **k: Any) -> Any:
            seen.append(k)
            if "temperature" in k:
                raise RuntimeError(
                    "Error code: 400 - `temperature` is deprecated for this model."
                )
            return _FakeResponse(model="claude-sonnet-5")

    class _Client:
        messages = _Msgs()

    try:
        with audit_logger.start_run("t"):
            result = run_agent("x", system="s",
                               messages=[{"role": "user", "content": "x"}],
                               tier=Tier.MID, client=_Client())
        assert result.text == "hello"
        assert "temperature" in seen[0]        # first attempt sent it
        assert "temperature" not in seen[1]    # retry dropped it
        assert "claude-sonnet-5" in agent_runtime._TEMPERATURE_UNSUPPORTED
    finally:
        agent_runtime._TEMPERATURE_UNSUPPORTED.discard("claude-sonnet-5")


def test_temperature_unsupported_model_skips_it_from_the_start(wired: _Recorder) -> None:
    """Once learned, the model omits `temperature` with no wasted first call."""
    agent_runtime._TEMPERATURE_UNSUPPORTED.add("claude-sonnet-5")
    seen: list[dict[str, Any]] = []

    class _Msgs:
        def count_tokens(self, **k: Any) -> Any:
            return SimpleNamespace(input_tokens=120)

        def create(self, **k: Any) -> Any:
            seen.append(k)
            return _FakeResponse(model="claude-sonnet-5")

    class _Client:
        messages = _Msgs()

    try:
        with audit_logger.start_run("t"):
            run_agent("x", system="s", messages=[{"role": "user", "content": "x"}],
                      tier=Tier.MID, client=_Client())
        assert len(seen) == 1                  # no retry needed
        assert "temperature" not in seen[0]
    finally:
        agent_runtime._TEMPERATURE_UNSUPPORTED.discard("claude-sonnet-5")
