"""
tests/test_generator_routing.py — the Router-composed prompt reaches the runtime.

Phase 4 hands ``generate_answer`` a ``RoutedPrompt``: the composed system prompt,
a persona/intent-aware ``max_tokens``, and the fragment ids to record. This
proves all three flow to the single call site, and that the legacy (un-routed)
default is unchanged so the eval harnesses keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from audit.logger import StepUsage
from rag import generator
from rag.agent_runtime import RuntimeResult, Tier
from rag.agents.prompt_router import route
from rag.generator import generate_answer


@dataclass
class _Capabilities:
    provider: str = "anthropic"
    supports_prompt_caching: bool = True
    supports_local_runtime: bool = False


class _RunAgentRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, agent_name: str, **kwargs: Any) -> RuntimeResult:
        self.calls.append((agent_name, kwargs))
        return RuntimeResult(
            text="Answer [dallas-code, chunk 4].", parsed_output=None,
            model=kwargs.get("model") or "ladder", stop_reason="end_turn",
            usage=StepUsage(tokens_in=100, tokens_out=50, cache_read=0, cache_write=0),
            autonomy_level="L3", latency_ms=10,
        )

    @property
    def kwargs(self) -> dict[str, Any]:
        return self.calls[-1][1]


def _chunk() -> dict[str, Any]:
    return {"id": uuid4(), "doc_id": "dallas-code", "chunk_index": 4,
            "municipality": "dallas", "authority_level": "municipal",
            "similarity": 0.9, "content": "Setbacks are 5 ft."}


@pytest.fixture()
def anthropic_env(monkeypatch: pytest.MonkeyPatch) -> _RunAgentRecorder:
    rec = _RunAgentRecorder()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(generator, "get_provider_capabilities", lambda: _Capabilities())
    monkeypatch.setattr(generator, "run_agent", rec)
    return rec


def test_routed_prompt_supplies_system_max_tokens_and_fragment_ids(
    anthropic_env: _RunAgentRecorder,
) -> None:
    routed = route(persona="diy", jurisdiction="dallas", intent="how_to")
    generate_answer("q", [_chunk()], routed=routed)
    kw = anthropic_env.kwargs
    assert kw["system"] == routed.system
    assert kw["max_tokens"] == routed.max_tokens  # persona/intent-aware, not 1024
    assert kw["max_tokens"] > 1024
    assert kw["prompt_fragment_ids"] == routed.fragment_ids
    assert kw["prompt_version"] == routed.library_version
    assert kw["tier"] is Tier.MID


def test_explicit_max_tokens_overrides_the_routed_ceiling(
    anthropic_env: _RunAgentRecorder,
) -> None:
    routed = route(persona="diy")
    generate_answer("q", [_chunk()], routed=routed, max_tokens=256)
    assert anthropic_env.kwargs["max_tokens"] == 256


def test_unrouted_default_is_unchanged(anthropic_env: _RunAgentRecorder) -> None:
    """No routed prompt → legacy 1024 fallback and no fragment ids (eval path)."""
    generate_answer("q", [_chunk()])
    kw = anthropic_env.kwargs
    assert kw["max_tokens"] == 1024
    assert kw["prompt_fragment_ids"] is None
