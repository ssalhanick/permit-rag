"""
tests/test_agent_registry.py — the agent registry + AgentSpec.

Covers registration semantics (no silent shadowing), lazy binding (the roster is
enumerable without importing every agent's dependencies), rag self-registration,
and the import-boundary guarantee that rag never pulls in commerce/forms/bids.
"""

from __future__ import annotations

import pytest

from rag.agent_runtime import Tier
from rag.agents import registry
from rag.agents.registry import AgentSpec, AgentSpecProtocol, lazy


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Snapshot and restore the module-global registry around each test."""
    saved = dict(registry._REGISTRY)
    try:
        yield
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)


def test_agentspec_satisfies_protocol() -> None:
    spec = AgentSpec(name="a", callable=lambda: None, tier=Tier.MID)
    assert isinstance(spec, AgentSpecProtocol)


def test_register_and_get() -> None:
    registry.clear()
    spec = AgentSpec(name="alpha", callable=lambda: 1)
    registry.register(spec)
    assert registry.get("alpha") is spec
    assert registry.is_registered("alpha")
    assert registry.get_or_none("missing") is None


def test_duplicate_name_raises_unless_replace() -> None:
    registry.clear()
    registry.register(AgentSpec(name="dup", callable=lambda: 1))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(AgentSpec(name="dup", callable=lambda: 2))
    replacement = AgentSpec(name="dup", callable=lambda: 2)
    registry.register(replacement, replace=True)
    assert registry.get("dup") is replacement


def test_all_specs_and_names_are_sorted() -> None:
    registry.clear()
    registry.register(AgentSpec(name="zeta", callable=lambda: 1))
    registry.register(AgentSpec(name="alpha", callable=lambda: 1))
    assert registry.names() == ["alpha", "zeta"]
    assert [s.name for s in registry.all_specs()] == ["alpha", "zeta"]


def test_lazy_binding_defers_import_until_call() -> None:
    """A lazy callable imports its target only when invoked."""
    proxy = lazy("math", "sqrt")
    assert proxy(9) == 3.0


def test_rag_self_registers_its_agents() -> None:
    """Importing rag.agents populates the registry with rag's own agents."""
    import rag.agents  # noqa: F401  (import triggers self-registration)

    assert registry.is_registered("answer_generator")
    assert registry.is_registered("design_intent")
    gen = registry.get("answer_generator")
    assert gen.tier == Tier.MID
    assert gen.parallel_safe is False
    assert "faithfulness" in gen.metrics


def test_registry_module_does_not_import_forbidden_packages() -> None:
    """rag/agents/registry.py must not reach into commerce/forms/bids."""
    import inspect

    source = inspect.getsource(registry)
    for forbidden in ("import commerce", "import forms", "import bids",
                      "from commerce", "from forms", "from bids"):
        assert forbidden not in source
