"""
rag/agents — the RAG-core agent package.

Importing this package self-registers the agents that live inside ``rag/``. The
callables are bound lazily (see :func:`rag.agents.registry.lazy`), so importing
the package to read the roster does not drag in each agent's heavy dependencies.

Agents backed by ``commerce/``, ``forms/``, or ``bids/`` are **not** registered
here — ``rag/`` cannot import those packages (AGENTS.md). ``api/main.py``
registers them at startup via dependency injection.

Phase 1 adds no new agents. It registers the two Anthropic-backed agents that
already exist so the registry has a real roster for Phase 2 to route through.
"""

from __future__ import annotations

from rag.agent_runtime import Tier
from rag.agents.registry import AgentSpec, lazy, register

# ── rag-owned agents (self-registered) ───────────────────────

_RAG_AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        name="answer_generator",
        callable=lazy("rag.generator", "generate_answer"),
        tier=Tier.MID,
        parallel_safe=False,  # terminal step: one answer per run
        metrics=("faithfulness", "answer_relevancy", "citation_density"),
    ),
    AgentSpec(
        name="design_intent",
        callable=lazy("rag.design_intent", "parse_design_intent"),
        tier=Tier.CHEAP,
        parallel_safe=True,
        metrics=("schema_validity", "overlay_precision"),
    ),
)


def _self_register() -> None:
    """Register rag's own agents, tolerating a re-import (replace=True)."""
    for spec in _RAG_AGENTS:
        register(spec, replace=True)


_self_register()
