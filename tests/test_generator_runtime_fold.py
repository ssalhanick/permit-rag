"""
tests/test_generator_runtime_fold.py — rag/generator.py folded into the runtime.

``rag/agent_runtime.py`` is the single Anthropic call site (AGENTS.md); the
generator was the last module still building its own client. Four things had to
be handled deliberately in the fold, and each has a test here because each one
silently changes production behaviour if it is got wrong:

a) the Ollama branch must not be routed through the Anthropic-only runtime,
b) tracing must move, not double — one step per call, on both branches,
c) ``LLM_MODEL`` is set in prod, so the ladder must not silently replace it,
d) ``max_tokens=1024`` stays as-is (persona-aware sizing is Phase 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from audit import logger as audit_logger
from audit.logger import StepUsage
from rag import agent_runtime, generator
from rag.agent_runtime import RuntimeResult, Tier
from rag.generator import generate_answer

# ── Fixtures ─────────────────────────────────────────────────


@dataclass
class _Capabilities:
    """Stand-in for rag.llm_provider.ProviderCapabilities."""

    provider: str = "anthropic"
    supports_prompt_caching: bool = True
    supports_local_runtime: bool = False


class _RunAgentRecorder:
    """Captures the kwargs the generator hands to the single call site."""

    def __init__(self, *, text: str = "Answer [dallas-code, chunk 4].") -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._text = text

    def __call__(self, agent_name: str, **kwargs: Any) -> RuntimeResult:
        self.calls.append((agent_name, kwargs))
        return RuntimeResult(
            text=self._text, parsed_output=None, model=kwargs.get("model") or "ladder",
            stop_reason="end_turn",
            usage=StepUsage(tokens_in=2655, tokens_out=400, cache_read=0, cache_write=0),
            autonomy_level="L3", latency_ms=1234,
        )

    @property
    def kwargs(self) -> dict[str, Any]:
        """Keyword arguments of the most recent call."""
        return self.calls[-1][1]


class _Recorder:
    """In-memory stand-in for db.client, capturing trace writes."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []

    def insert_agent_run(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": uuid4(), **kwargs}
        self.runs.append(row)
        return row

    def finish_agent_run(self, run_id: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": run_id}

    def annotate_agent_run(self, run_id: Any, **kwargs: Any) -> dict[str, Any]:
        return {"id": run_id}

    def insert_agent_step(self, **kwargs: Any) -> dict[str, Any]:
        row = {"id": uuid4(), **kwargs}
        self.steps.append(row)
        return row

    def get_agent_autonomy(self, agent_name: str, scope: str = "default") -> Any:
        return None


def _chunk(doc_id: str = "dallas-code", index: int = 4, **extra: Any) -> dict[str, Any]:
    """A retrieved chunk row."""
    return {"id": uuid4(), "doc_id": doc_id, "chunk_index": index,
            "municipality": "dallas", "authority_level": "municipal",
            "similarity": 0.88, "content": "Setbacks are 5 ft.", **extra}


@pytest.fixture()
def anthropic_env(monkeypatch: pytest.MonkeyPatch) -> _RunAgentRecorder:
    """Anthropic provider, a key present, and run_agent swapped for a recorder."""
    recorder = _RunAgentRecorder()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(generator, "get_provider_capabilities", lambda: _Capabilities())
    monkeypatch.setattr(generator, "run_agent", recorder)
    return recorder


# ── (a) the Ollama branch stays local ────────────────────────


def test_local_runtime_never_reaches_the_anthropic_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_agent is Anthropic-only; LLM_PROVIDER=ollama must bypass it entirely."""
    recorder = _RunAgentRecorder()
    monkeypatch.setattr(generator, "run_agent", recorder)
    monkeypatch.setattr(
        generator, "get_provider_capabilities",
        lambda: _Capabilities(provider="ollama", supports_local_runtime=True,
                              supports_prompt_caching=False),
    )
    import requests

    monkeypatch.setattr(
        requests, "post",
        lambda *_a, **_k: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "Local answer."},
                          "prompt_eval_count": 10, "eval_count": 5, "model": "qwen2.5"},
        ),
    )
    result = generate_answer("q", [_chunk()])

    assert recorder.calls == []
    assert result.answer == "Local answer."
    assert result.model == "qwen2.5"


def test_local_runtime_still_records_exactly_one_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Trap (b), local half.

    @traced moved off generate_answer onto the Ollama helper. If it had simply
    been deleted, the local path would have silently stopped tracing.
    """
    recorder = _Recorder()
    monkeypatch.setattr(audit_logger, "db_client", recorder)
    monkeypatch.setattr(
        generator, "get_provider_capabilities",
        lambda: _Capabilities(provider="ollama", supports_local_runtime=True,
                              supports_prompt_caching=False),
    )
    import requests

    monkeypatch.setattr(
        requests, "post",
        lambda *_a, **_k: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "Local."}, "prompt_eval_count": 10,
                          "eval_count": 5, "model": "qwen2.5"},
        ),
    )
    with audit_logger.start_run("t"):
        generate_answer("q", [_chunk()])

    assert [s["agent_name"] for s in recorder.steps] == ["answer_generator"]


# ── (b) tracing moved, it did not double ─────────────────────


class _FakeAnthropic:
    """Minimal Anthropic client: count_tokens + messages.create."""

    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(
            count_tokens=lambda **_k: SimpleNamespace(input_tokens=2655),
            create=self._create,
        )

    def _create(self, **kwargs: Any) -> Any:
        self.created.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(text="Answer [dallas-code, chunk 4].")],
            model=kwargs["model"], stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=2655, output_tokens=400,
                                  cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
        )


def test_anthropic_path_records_exactly_one_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Trap (b), the expensive half.

    ``run_agent`` records a step. Leaving ``@traced`` on ``generate_answer`` too
    would have counted every production answer twice — the exact mistake
    design_intent hit in Phase 1 — inflating cost and call-count on every
    scorecard built on this table.
    """
    recorder = _Recorder()
    client = _FakeAnthropic()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(audit_logger, "db_client", recorder)
    monkeypatch.setattr(agent_runtime, "db_client", recorder)
    monkeypatch.setattr(agent_runtime, "_build_client", lambda _c: client)
    monkeypatch.setattr(generator, "get_provider_capabilities", lambda: _Capabilities())

    with audit_logger.start_run("t"):
        result = generate_answer("q", [_chunk()])

    assert [s["agent_name"] for s in recorder.steps] == ["answer_generator"]
    assert result.input_tokens == 2655 and result.output_tokens == 400
    assert result.stop_reason == "end_turn"


def test_generate_answer_no_longer_carries_the_traced_decorator() -> None:
    """A re-added decorator would silently restore double counting."""
    assert not hasattr(generate_answer, "__wrapped__")


# ── (c) LLM_MODEL still wins ─────────────────────────────────


def test_env_model_is_passed_through_as_an_explicit_override(
    anthropic_env: _RunAgentRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Trap (c). LLM_MODEL is set in prod (terraform: claude-haiku-4-5-20251001).

    Letting the MID rung decide instead would have swapped haiku for sonnet —
    a different model and roughly 3x the generation cost — inside the one phase
    that forbids behaviour changes.
    """
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["model"] == "claude-haiku-4-5-20251001"


def test_default_model_matches_the_pre_fold_default(
    anthropic_env: _RunAgentRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With LLM_MODEL unset, the same dated haiku id the old code defaulted to."""
    monkeypatch.delenv("LLM_MODEL", raising=False)
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["model"] == "claude-haiku-4-5-20251001"


def test_explicit_model_argument_still_beats_the_environment(
    anthropic_env: _RunAgentRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The eval harnesses pass model= directly; that precedence is unchanged."""
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    generate_answer("q", [_chunk()], model="claude-sonnet-5")
    assert anthropic_env.kwargs["model"] == "claude-sonnet-5"


def test_registry_tier_is_still_declared(anthropic_env: _RunAgentRecorder) -> None:
    """The ladder rung is recorded even while the override decides the wire model."""
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["tier"] is Tier.MID


# ── (d) max_tokens is left alone ─────────────────────────────


def test_max_tokens_is_still_1024(anthropic_env: _RunAgentRecorder) -> None:
    """
    Trap (d), deliberately NOT fixed here.

    1024 will truncate diy and hiring_contractor answers once Phase 4's persona
    fragments land. Making it persona-aware is Phase 4's job; changing it now
    would be a behaviour change in the phase that forbids them.
    """
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["max_tokens"] == 1024


def test_caller_supplied_max_tokens_is_honoured(
    anthropic_env: _RunAgentRecorder,
) -> None:
    """Phase 4 needs this hook to already work."""
    generate_answer("q", [_chunk()], max_tokens=4096)
    assert anthropic_env.kwargs["max_tokens"] == 4096


# ── Caching decision, set deliberately ───────────────────────


def test_cache_system_follows_the_existing_operator_switch(
    anthropic_env: _RunAgentRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANTHROPIC_PROMPT_CACHE_ENABLED keeps its meaning; default is off."""
    monkeypatch.delenv("ANTHROPIC_PROMPT_CACHE_ENABLED", raising=False)
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["cache_system"] is False

    monkeypatch.setenv("ANTHROPIC_PROMPT_CACHE_ENABLED", "true")
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["cache_system"] is True


def test_cache_is_refused_when_the_provider_cannot_do_it(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider without caching support overrides the operator's request."""
    recorder = _RunAgentRecorder()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_PROMPT_CACHE_ENABLED", "true")
    monkeypatch.setattr(generator, "run_agent", recorder)
    monkeypatch.setattr(
        generator, "get_provider_capabilities",
        lambda: _Capabilities(supports_prompt_caching=False),
    )
    generate_answer("q", [_chunk()])
    assert recorder.kwargs["cache_system"] is False


def test_cache_ttl_env_selects_the_one_hour_tier(
    anthropic_env: _RunAgentRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANTHROPIC_PROMPT_CACHE_TTL=1h maps onto the runtime's cache_ttl_1h flag."""
    monkeypatch.setenv("ANTHROPIC_PROMPT_CACHE_TTL", "1h")
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["cache_ttl_1h"] is True

    monkeypatch.setenv("ANTHROPIC_PROMPT_CACHE_TTL", "5m")
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["cache_ttl_1h"] is False


# ── The contract callers depend on is unchanged ──────────────


def test_generation_result_shape_survives_the_fold(
    anthropic_env: _RunAgentRecorder,
) -> None:
    """Every field the route, evals, and audit.usage_from read is still populated."""
    result = generate_answer("q", [_chunk()])

    assert result.query == "q"
    assert result.chunk_count == 1
    assert result.latency_ms == 1234
    assert result.cache_read_input_tokens == 0
    assert result.cache_creation_input_tokens == 0
    assert [c["doc_id"] for c in result.citations] == ["dallas-code"]
    assert result.citations[0]["found_in_context"] is True


def test_filtered_chunks_are_still_dropped_before_prompting(
    anthropic_env: _RunAgentRecorder,
) -> None:
    """Phase 0's defect #2 fix lives inside generate_answer and must survive."""
    generate_answer(
        "q", [_chunk("keep", 1), _chunk("rejected", 2, filtered_out=True)]
    )
    prompt = anthropic_env.kwargs["messages"][0]["content"]

    assert "keep" in prompt
    assert "rejected" not in prompt


def test_missing_api_key_still_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The route turns this RuntimeError into a 500 with the message verbatim."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(generator, "get_provider_capabilities", lambda: _Capabilities())
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        generate_answer("q", [_chunk()])


def test_prompt_version_reaches_the_trace(anthropic_env: _RunAgentRecorder) -> None:
    """Prompt changes must stay correlatable with quality shifts."""
    generate_answer("q", [_chunk()])
    assert anthropic_env.kwargs["prompt_version"] == generator.PROMPT_VERSION


# ── The kickoff chat folded too ──────────────────────────────


def test_kickoff_chat_goes_through_the_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The second inline client in this module.

    AGENTS.md's "no inline anthropic calls" rule is per-module, not
    per-function, so this was folded alongside generate_answer.
    """
    recorder = _RunAgentRecorder(text='{"is_complete": true, "persona": "contractor"}')
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setattr(generator, "run_agent", recorder)
    monkeypatch.setattr(generator, "get_provider_capabilities", lambda: _Capabilities())

    result = generator.generate_kickoff_chat_response(
        [{"role": "user", "content": "I am a contractor"}], address="1 Main St"
    )
    assert result["persona"] == "contractor"
    assert recorder.calls[-1][0] == "kickoff_chat"
    assert recorder.kwargs["model"] == "claude-haiku-4-5-20251001"
    assert recorder.kwargs["cache_system"] is False


def test_no_module_builds_its_own_anthropic_client() -> None:
    """
    AGENTS.md: rag/agent_runtime.py is the only permitted call site.

    A grep test rather than a mock, because the failure mode is a *new* call
    site appearing somewhere the mocks do not reach.
    """
    from pathlib import Path

    root = Path(generator.__file__).resolve().parent.parent
    offenders = []
    for path in sorted((root / "rag").rglob("*.py")):
        if path.name == "agent_runtime.py":
            continue
        if "anthropic.Anthropic(" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == []
