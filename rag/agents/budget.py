"""
rag/agents/budget.py — the Budget Governor
===========================================
Phase 2 of the agent architecture. Agent #3 in the roster, and the only Tier 0
agent that is **not an LLM**. It owns three deterministic decisions:

1. **Per-request token cap** — how many input tokens one request may spend.
2. **Ladder selection** — which model tier a plan step runs on.
3. **Degradation** — when a step would breach the cap, shed the cheapest-value
   context (lowest-ranked chunks first) rather than failing the request.

Asking a model to decide any of these would cost tokens to decide how to spend
tokens, and would make the spend non-reproducible. Every method here is a pure
function of its inputs and the policy.

**Phase 2 ships this uncapped by default, deliberately.** ``max_input_tokens``
is None unless ``AGENT_BUDGET_MAX_INPUT_TOKENS`` is set, so :meth:`plan_step`
always allows and :meth:`degrade` never drops a chunk. That is what keeps this
phase behaviour-free: the governor is wired, measured, and traced, but it
changes nothing until an operator sets a cap. Phase 4 turns it on alongside
persona-aware ``max_tokens``.

**Ladder selection is advisory this phase.** ``rag/generator.py`` still resolves
its model from ``LLM_MODEL`` and passes it to ``run_agent`` as an explicit
override — see the fold note in that module. :meth:`tier_for` therefore records
the ladder's *opinion* on a step without yet dictating the wire model. Phase 4
removes the override and lets this decide.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from rag.agent_runtime import Tier

log = logging.getLogger(__name__)

_CAP_ENV = "AGENT_BUDGET_MAX_INPUT_TOKENS"

# Which rung each plan step runs on. Mirrors the "Balanced" column of the cost
# model in docs/agent_architecture.md: cheap orchestration, mid generation.
_DEFAULT_TIERS: dict[str, Tier] = {
    "manager": Tier.CHEAP,
    "answer_generator": Tier.MID,
    "design_intent": Tier.CHEAP,
    "permit_classifier": Tier.CHEAP,
    "conflict_detector": Tier.CHEAP,
}


class BudgetExceededError(RuntimeError):
    """Raised when a step cannot fit the cap even after degradation."""


@dataclass(frozen=True)
class BudgetPolicy:
    """
    The knobs, all deterministic.

    Args:
        max_input_tokens: Ceiling on estimated input tokens for one request.
            None means uncapped — Phase 2's default and the reason this phase
            is behaviour-free.
        min_chunks: Degradation floor. Never shed below this many chunks; an
            answer grounded in one chunk is worse than a slow one, and
            AGENTS.md requires every answer to carry a citation.
        tiers: Step name → ladder tier.
    """

    max_input_tokens: int | None = None
    min_chunks: int = 3
    tiers: dict[str, Tier] = field(default_factory=lambda: dict(_DEFAULT_TIERS))


@dataclass(frozen=True)
class BudgetDecision:
    """One governor verdict, recorded on the Manager's trace step."""

    step: str
    tier: Tier
    estimated_tokens: int
    allowed: bool
    degraded: bool = False
    dropped: int = 0
    reason: str = ""


def policy_from_env() -> BudgetPolicy:
    """
    Build a policy from the environment, defaulting to uncapped.

    An unparseable ``AGENT_BUDGET_MAX_INPUT_TOKENS`` degrades to uncapped with a
    warning rather than raising: a malformed cost knob must not take down the
    answer path.
    """
    raw = os.environ.get(_CAP_ENV, "").strip()
    if not raw:
        return BudgetPolicy()
    try:
        cap = int(raw)
    except ValueError:
        log.warning("%s=%r is not an integer; running uncapped", _CAP_ENV, raw)
        return BudgetPolicy()
    if cap <= 0:
        return BudgetPolicy()
    return BudgetPolicy(max_input_tokens=cap)


class BudgetGovernor:
    """
    Per-request token accounting. Not an LLM; every method is a pure decision.

    One instance per request. It accumulates what the plan has already spent so
    a late step sees the remaining headroom rather than the full cap.
    """

    def __init__(self, policy: BudgetPolicy | None = None) -> None:
        """Create a governor over ``policy`` (env-derived when omitted)."""
        self.policy = policy or policy_from_env()
        self.spent_tokens = 0
        self.decisions: list[BudgetDecision] = []

    @property
    def capped(self) -> bool:
        """True when a per-request ceiling is configured."""
        return self.policy.max_input_tokens is not None

    @property
    def remaining(self) -> int | None:
        """Headroom left in the cap, or None when uncapped."""
        if self.policy.max_input_tokens is None:
            return None
        return max(0, self.policy.max_input_tokens - self.spent_tokens)

    def tier_for(self, step: str) -> Tier:
        """Ladder rung for a plan step; unknown steps run cheap."""
        return self.policy.tiers.get(step, Tier.CHEAP)

    def plan_step(self, step: str, estimated_tokens: int) -> BudgetDecision:
        """
        Decide whether a step may run at its estimated size, and record it.

        Uncapped policies always allow — that is Phase 2's no-op default.
        """
        tier = self.tier_for(step)
        headroom = self.remaining
        allowed = headroom is None or estimated_tokens <= headroom
        decision = BudgetDecision(
            step=step,
            tier=tier,
            estimated_tokens=estimated_tokens,
            allowed=allowed,
            reason="" if allowed else f"needs {estimated_tokens}, {headroom} left",
        )
        self.decisions.append(decision)
        return decision

    def degrade(
        self, step: str, chunks: list[dict[str, Any]], *, overhead_tokens: int = 0
    ) -> tuple[list[dict[str, Any]], BudgetDecision]:
        """
        Shed the lowest-ranked chunks until the step fits, floored at min_chunks.

        Ranking is ``reranked_score`` then ``similarity`` — the reranker already
        decided what matters, so the governor never re-judges relevance, it only
        truncates the tail. Returns the surviving chunks and the verdict.
        """
        from rag.agents.artifacts import estimate_tokens

        tier = self.tier_for(step)
        headroom = self.remaining
        if headroom is None:  # uncapped: do not even pay to measure
            return chunks, self._record(step, tier, 0, allowed=True)
        estimated = estimate_tokens(chunks) + overhead_tokens
        if estimated <= headroom:
            return chunks, self._record(step, tier, estimated, allowed=True)

        kept = sorted(chunks, key=_rank_key, reverse=True)
        while len(kept) > self.policy.min_chunks and estimated > headroom:
            kept.pop()
            estimated = estimate_tokens(kept) + overhead_tokens
        dropped = len(chunks) - len(kept)
        decision = self._record(
            step, tier, estimated, allowed=estimated <= headroom,
            degraded=dropped > 0, dropped=dropped,
        )
        if not decision.allowed:
            raise BudgetExceededError(
                f"{step} needs {estimated} tokens with {len(kept)} chunks; "
                f"{headroom} left and the {self.policy.min_chunks}-chunk floor is reached"
            )
        return kept, decision

    def _record(
        self,
        step: str,
        tier: Tier,
        estimated: int,
        *,
        allowed: bool,
        degraded: bool = False,
        dropped: int = 0,
    ) -> BudgetDecision:
        """Append a decision to this request's ledger and return it."""
        reason = f"shed {dropped} chunk(s) to fit" if degraded else ""
        decision = BudgetDecision(
            step=step, tier=tier, estimated_tokens=estimated, allowed=allowed,
            degraded=degraded, dropped=dropped, reason=reason,
        )
        self.decisions.append(decision)
        return decision

    def charge(self, tokens_in: int, tokens_out: int = 0) -> None:
        """Record actual measured spend after a step ran."""
        self.spent_tokens += max(0, tokens_in) + max(0, tokens_out)


def _rank_key(chunk: dict[str, Any]) -> float:
    """Sort key for degradation — the reranker's score, then raw similarity."""
    score = chunk.get("reranked_score")
    if isinstance(score, int | float):
        return float(score)
    similarity = chunk.get("similarity")
    return float(similarity) if isinstance(similarity, int | float) else 0.0
