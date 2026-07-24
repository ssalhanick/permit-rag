"""
tests/test_agent_budget.py — the Budget Governor.

Two things matter here. First, that the governor is genuinely deterministic —
it is the one Tier 0 agent that is not an LLM, and a non-reproducible spend
decision would defeat the point. Second, that Phase 2's default is a **no-op**:
uncapped, it must never drop a chunk or change a tier, because that is what
makes this phase's faithfulness numbers attributable to the abstraction.
"""

from __future__ import annotations

from typing import Any

import pytest

from rag.agent_runtime import Tier
from rag.agents.budget import (
    BudgetExceededError,
    BudgetGovernor,
    BudgetPolicy,
    policy_from_env,
)


def _chunk(doc_id: str, score: float, *, size: int = 1500) -> dict[str, Any]:
    """A retrieved chunk with a reranker score and realistic content length."""
    return {"doc_id": doc_id, "reranked_score": score, "content": "x" * size}


# ── The Phase 2 default: uncapped, therefore a no-op ─────────


def test_default_policy_is_uncapped() -> None:
    """No cap configured means the governor changes nothing this phase."""
    governor = BudgetGovernor(BudgetPolicy())
    assert governor.capped is False
    assert governor.remaining is None


def test_uncapped_degrade_returns_every_chunk_untouched() -> None:
    """The behaviour-preservation guarantee, asserted directly."""
    chunks = [_chunk(f"doc-{i}", 0.9 - i / 10) for i in range(10)]
    kept, decision = BudgetGovernor(BudgetPolicy()).degrade("answer_generator", chunks)

    assert kept == chunks
    assert decision.allowed is True
    assert decision.degraded is False
    assert decision.dropped == 0


def test_uncapped_plan_step_always_allows() -> None:
    """Even an absurd estimate passes when there is no ceiling."""
    assert BudgetGovernor(BudgetPolicy()).plan_step("answer_generator", 10**9).allowed


# ── Ladder selection ─────────────────────────────────────────


def test_tier_ladder_matches_the_balanced_cost_model() -> None:
    """Cheap orchestration, mid generation (docs/agent_architecture.md)."""
    governor = BudgetGovernor(BudgetPolicy())
    assert governor.tier_for("manager") is Tier.CHEAP
    assert governor.tier_for("answer_generator") is Tier.MID


def test_unknown_step_runs_cheap() -> None:
    """An unbudgeted new agent must not silently land on opus."""
    assert BudgetGovernor(BudgetPolicy()).tier_for("brand_new_agent") is Tier.CHEAP


# ── Degradation, once a cap exists ───────────────────────────


def test_degrade_sheds_the_lowest_ranked_chunks_first() -> None:
    """The reranker already judged relevance; the governor only truncates the tail."""
    chunks = [_chunk("keep-a", 0.9), _chunk("drop", 0.1), _chunk("keep-b", 0.8)]
    governor = BudgetGovernor(BudgetPolicy(max_input_tokens=800, min_chunks=2))
    kept, decision = governor.degrade("answer_generator", chunks)

    assert [c["doc_id"] for c in kept] == ["keep-a", "keep-b"]
    assert decision.degraded is True
    assert decision.dropped == 1


def test_degradation_stops_at_the_min_chunks_floor() -> None:
    """Below the floor an answer cannot carry a citation — fail instead of shedding."""
    chunks = [_chunk(f"doc-{i}", 0.5) for i in range(6)]
    governor = BudgetGovernor(BudgetPolicy(max_input_tokens=100, min_chunks=3))
    with pytest.raises(BudgetExceededError):
        governor.degrade("answer_generator", chunks)


def test_a_fitting_request_is_not_degraded_even_when_capped() -> None:
    """A cap only bites when it is actually breached."""
    chunks = [_chunk("small", 0.9, size=40)]
    governor = BudgetGovernor(BudgetPolicy(max_input_tokens=50_000))
    kept, decision = governor.degrade("answer_generator", chunks)

    assert kept == chunks
    assert decision.degraded is False


def test_spend_reduces_headroom_for_later_steps() -> None:
    """A late step sees what the plan already spent, not the full cap."""
    governor = BudgetGovernor(BudgetPolicy(max_input_tokens=1000))
    governor.charge(300, 200)
    assert governor.remaining == 500
    assert governor.plan_step("answer_generator", 600).allowed is False


def test_decisions_are_recorded_for_the_trace() -> None:
    """Every verdict lands on the ledger the Manager step reports."""
    governor = BudgetGovernor(BudgetPolicy())
    governor.plan_step("manager", 10)
    governor.degrade("answer_generator", [_chunk("a", 0.9)])
    assert [d.step for d in governor.decisions] == ["manager", "answer_generator"]


# ── Env parsing ──────────────────────────────────────────────


def test_env_cap_is_read_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The operator knob is the only way a cap turns on."""
    monkeypatch.setenv("AGENT_BUDGET_MAX_INPUT_TOKENS", "12000")
    assert policy_from_env().max_input_tokens == 12000


def test_malformed_env_cap_degrades_to_uncapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in a cost knob must not take down the answer path."""
    monkeypatch.setenv("AGENT_BUDGET_MAX_INPUT_TOKENS", "twelve thousand")
    assert policy_from_env().max_input_tokens is None


def test_unset_env_is_uncapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 2's shipped default."""
    monkeypatch.delenv("AGENT_BUDGET_MAX_INPUT_TOKENS", raising=False)
    assert policy_from_env().max_input_tokens is None
