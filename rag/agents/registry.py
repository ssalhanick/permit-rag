"""
rag/agents/registry.py — the agent registry
============================================
Phase 1 of the agent architecture. Every agent the Manager can route to is an
:class:`AgentSpec`: a name, the callable that runs it, its ladder tier, whether
it is safe to fan out in parallel, and the metric names the Evaluator scores it
against. The registry is the one place that knows the full roster.

**Dependency injection across the import boundary.** ``rag/`` may not import
``commerce/``, ``forms/``, or ``bids/`` (AGENTS.md). So ``rag`` self-registers
its own agents on import, and ``api/main.py`` — which *is* allowed to import
everything — registers the commerce-, forms-, and bids-backed agents at startup.
The registry itself imports nothing from those packages; it just holds specs.

To keep importing the registry cheap, an agent's callable can be **lazily
bound** with :func:`lazy` — the target module is imported on first call, not at
registration. That lets the Manager enumerate the roster without dragging in
every agent's transitive dependencies.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from rag.agent_runtime import Tier


@runtime_checkable
class AgentSpecProtocol(Protocol):
    """Structural contract every registered agent satisfies."""

    name: str
    callable: Callable[..., Any]
    tier: Tier
    parallel_safe: bool
    metrics: tuple[str, ...]


@dataclass(frozen=True)
class AgentSpec:
    """
    One routable agent.

    Args:
        name: Unique registry key, also the ``agent_name`` used in traces and in
            ``agent_autonomy`` — they must match for autonomy to apply.
        callable: The function that runs the agent. May be a real function or a
            lazy proxy from :func:`lazy`.
        tier: Default model-ladder tier (agents may still override per call).
        parallel_safe: True if the Manager may fan this agent out concurrently.
        metrics: Metric-contract names the Evaluator scores (docs, Phase 5).
    """

    name: str
    callable: Callable[..., Any]
    tier: Tier = Tier.CHEAP
    parallel_safe: bool = True
    metrics: tuple[str, ...] = field(default_factory=tuple)


def lazy(module: str, attr: str) -> Callable[..., Any]:
    """
    Return a proxy that imports ``module`` and calls ``module.attr`` on first use.

    Registration stays cheap: the heavy import happens only when the agent is
    actually invoked, not when the registry is populated.
    """

    def _proxy(*args: Any, **kwargs: Any) -> Any:
        target = getattr(importlib.import_module(module), attr)
        return target(*args, **kwargs)

    _proxy.__name__ = f"{attr}_lazy"
    _proxy.__qualname__ = f"{module}.{attr}"
    return _proxy


# ── Registry state ───────────────────────────────────────────

_REGISTRY: dict[str, AgentSpec] = {}


def register(spec: AgentSpec, *, replace: bool = False) -> AgentSpec:
    """
    Add a spec to the registry.

    Duplicate names raise unless ``replace=True`` — a silent overwrite would let
    one package shadow another's agent and be near-impossible to debug.
    """
    if spec.name in _REGISTRY and not replace:
        raise ValueError(f"agent {spec.name!r} is already registered")
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> AgentSpec:
    """Return the spec for ``name``; raise ``KeyError`` if it is not registered."""
    return _REGISTRY[name]


def get_or_none(name: str) -> AgentSpec | None:
    """Return the spec for ``name``, or None when it is not registered."""
    return _REGISTRY.get(name)


def is_registered(name: str) -> bool:
    """True if an agent named ``name`` is in the registry."""
    return name in _REGISTRY


def all_specs() -> list[AgentSpec]:
    """Every registered spec, sorted by name for stable enumeration."""
    return [_REGISTRY[n] for n in sorted(_REGISTRY)]


def names() -> list[str]:
    """Every registered agent name, sorted."""
    return sorted(_REGISTRY)


def unregister(name: str) -> None:
    """Remove one spec if present (primarily for tests and hot-reload)."""
    _REGISTRY.pop(name, None)


def clear() -> None:
    """Empty the registry — test-support only."""
    _REGISTRY.clear()
