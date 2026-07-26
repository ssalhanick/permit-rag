"""
rag/agents — the RAG-core agent package.

Importing this package self-registers the agents that live inside ``rag/``. The
callables are bound lazily (see :func:`rag.agents.registry.lazy`), so importing
the package to read the roster does not drag in each agent's heavy dependencies.

Agents backed by ``commerce/``, ``forms/``, or ``bids/`` are **not** registered
here — ``rag/`` cannot import those packages (AGENTS.md). ``api/main.py``
registers them at startup via dependency injection.

Phase 1 registered the two Anthropic-backed agents. Phase 2 adds the Manager,
the Budget Governor, and the deterministic proto-agents the Manager delegates
to — all of which already existed as loose functions in ``rag/``. **No new
capability is introduced**: registering an existing function is what lets the
Manager route to it, and lazy binding is what keeps a monkeypatched module
attribute (as several tests rely on) still visible at call time.
"""

from __future__ import annotations

from rag.agent_runtime import Tier
from rag.agents.registry import AgentSpec, lazy, register

# ── rag-owned agents (self-registered) ───────────────────────

_RAG_AGENTS: tuple[AgentSpec, ...] = (
    # Tier 0 — control
    AgentSpec(
        name="manager",
        callable=lazy("rag.agents.manager", "run_query_plan"),
        tier=Tier.CHEAP,
        parallel_safe=False,  # one orchestrator per run, by definition
        metrics=("routing_accuracy", "plan_length", "replan_rate", "react_iterations"),
    ),
    AgentSpec(
        name="budget_governor",
        callable=lazy("rag.agents.budget", "BudgetGovernor"),
        tier=Tier.CHEAP,  # nominal: the governor is deterministic, never a call
        parallel_safe=True,
        metrics=("budget_trips", "degradation_rate"),
    ),
    AgentSpec(
        name="prompt_router",
        callable=lazy("rag.agents.prompt_router", "route"),
        tier=Tier.CHEAP,  # deterministic: fragment lookup, never a model call
        parallel_safe=True,
        metrics=(
            "fragment_selection_accuracy",
            "persona_appropriateness",
            "default_to_research_rate",
        ),
    ),
    AgentSpec(
        name="guardrail",
        callable=lazy("rag.agents.guardrail", "check_truncation"),
        tier=Tier.CHEAP,  # deterministic checks; L3 by design (a blocker, not a proposer)
        parallel_safe=True,
        metrics=("guard_trip_rate",),
    ),
    # Tier 1 — answer path
    AgentSpec(
        name="answer_generator",
        callable=lazy("rag.generator", "generate_answer"),
        tier=Tier.MID,
        parallel_safe=False,  # terminal step: one answer per run
        metrics=("faithfulness", "answer_relevancy", "citation_density"),
    ),
    AgentSpec(
        name="permit_classifier",
        callable=lazy("rag.permit_classifier", "classify_permit_types"),
        tier=Tier.CHEAP,  # deterministic today (NLI + keyword), no model call
        parallel_safe=True,
        metrics=("permit_type_f1",),
    ),
    AgentSpec(
        name="jurisdiction_resolver",
        callable=lazy("rag.jurisdiction_resolver", "municipality_from_address"),
        tier=Tier.CHEAP,
        parallel_safe=True,
        metrics=("municipality_accuracy",),
    ),
    AgentSpec(
        name="conflict_detector",
        callable=lazy("rag.conflict_detector", "detect_conflicts"),
        tier=Tier.CHEAP,
        parallel_safe=True,
        metrics=("detection_precision", "false_alarm_rate"),
    ),
    AgentSpec(
        name="citation_verifier",
        callable=lazy("rag.agents.citation_verifier", "verify_answer"),
        tier=Tier.MID,  # deterministic span match first, entailment only on leftovers
        parallel_safe=True,  # reads (answer + chunks); post-generation, ∥ conflict analyzer
        metrics=("claim_precision", "claim_recall"),
    ),
    AgentSpec(
        name="query_deconstructor",
        callable=lazy("rag.agents.deconstructor", "deconstruct"),
        tier=Tier.CHEAP,  # single-shot extraction, gated by a deterministic heuristic
        parallel_safe=True,  # pre-retrieval; enables one retrieval per sub-question
        metrics=("sub_question_coverage", "filter_precision"),
    ),
    AgentSpec(
        name="permit_strategy",
        callable=lazy("rag.agents.permit_strategy", "plan_permits"),
        tier=Tier.CHEAP,  # permit set/order/fees deterministic; only the note is a call
        parallel_safe=True,
        metrics=("permit_set_f1",),
    ),
    AgentSpec(
        name="mini_rag_conflicts",
        callable=lazy("rag.mini_rag", "detect_corpus_upload_conflicts"),
        tier=Tier.CHEAP,
        parallel_safe=True,
        metrics=("detection_precision",),
    ),
    AgentSpec(
        name="project_context",
        callable=lazy("rag.project_context", "load_project_context"),
        tier=Tier.CHEAP,
        parallel_safe=True,
        metrics=("fact_coverage",),
    ),
    # Tier 2 — action agents
    AgentSpec(
        name="design_intent",
        callable=lazy("rag.design_intent", "parse_design_intent"),
        tier=Tier.CHEAP,
        parallel_safe=True,
        metrics=("schema_validity", "overlay_precision"),
    ),
    AgentSpec(
        name="media_curator",
        callable=lazy("rag.agents.media", "curate"),
        tier=Tier.CHEAP,  # deterministic media_refs lookup; no model call (B1)
        parallel_safe=True,  # runs ∥ answer_generator on the diy path
        metrics=("link_liveness", "relevance", "zero_unsourced_urls"),
    ),
)


def _self_register() -> None:
    """Register rag's own agents, tolerating a re-import (replace=True)."""
    for spec in _RAG_AGENTS:
        register(spec, replace=True)


_self_register()
