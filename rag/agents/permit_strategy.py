"""
rag/agents/permit_strategy.py — Permit Strategy (agent #11)
==========================================================
Phase 5 answer-path agent. Turns a project's context (work types, jurisdiction)
into a **permit set + sequencing + fee estimate**. The permit *set* is the same
mapping the kickoff wizard already uses (``frontend/src/projectPermitRules.js``),
mirrored here so the two never drift — that is what the metric contract measures
(permit-set F1 vs. that file). The agent's value-add over the wizard is the
**order** the permits must be pulled and a rough **fee** total, neither of which
the JS produces.

**Deterministic by construction.** The permit set, the pull order, and the base
fees are all table lookups — no model, no drift from the ground truth. An
optional single call adds a short project-specific sequencing note; it degrades
to a templated note when off or on failure, so the numbers never depend on the
model.

Fees are explicitly **estimates** (flat DFW-ish placeholders), never quoted as an
AHJ's actual schedule — the disclaimer says so. Import boundary: rag/agents/ →
rag/, db/, audit/, standard library. Model calls via ``run_agent``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from rag.agent_runtime import Tier, run_agent

log = logging.getLogger(__name__)

AGENT_NAME = "permit_strategy"

# Mirror of WORK_TYPE_TO_PERMITS in frontend/src/projectPermitRules.js. Keep in
# lockstep — the metric contract is permit-set F1 against that file.
_WORK_TYPE_TO_PERMITS: dict[str, tuple[str, ...]] = {
    "Plumbing": ("Plumbing",),
    "Electrical": ("Electrical",),
    "HVAC / Mechanical": ("Mechanical",),
    "Structural / Framing": ("Building",),
    "Roofing": ("Building", "Roofing"),
    "Deck / Patio Build": ("Building", "Zoning"),
    "Pool / Spa": ("Building", "Zoning", "Electrical", "Plumbing"),
    "Demolition": ("Building", "Demolition"),
    "Windows / Doors": ("Building",),
    "Paint / Drywall": (),
    "Flooring": (),
    "Tile / Backsplash": (),
}

# Pull order (lower = earlier). Demolition and zoning clear the site/use first;
# the trade rough-ins follow the building permit; roofing closes it out.
_SEQUENCE_RANK: dict[str, int] = {
    "Demolition": 0,
    "Zoning": 1,
    "Building": 2,
    "Plumbing": 3,
    "Mechanical": 3,
    "Electrical": 3,
    "Roofing": 4,
}

# Flat base-fee ESTIMATES in USD — placeholders, not any AHJ's real schedule.
_BASE_FEES: dict[str, int] = {
    "Building": 150,
    "Electrical": 75,
    "Plumbing": 75,
    "Mechanical": 75,
    "Roofing": 100,
    "Zoning": 120,
    "Demolition": 90,
}

FEE_DISCLAIMER = (
    "Fee figures are rough planning estimates, not a quote — the AHJ sets actual "
    "fees (often valuation-based). Verify with the building department."
)


@dataclass
class PermitStrategy:
    """A project's recommended permits, in pull order, with a fee estimate."""

    permits: list[str] = field(default_factory=list)
    sequence: list[str] = field(default_factory=list)
    fee_breakdown: dict[str, int] = field(default_factory=dict)
    estimated_fees_usd: int = 0
    notes: str = ""
    fee_disclaimer: str = FEE_DISCLAIMER


def recommend_permits(work_types: list[str] | None) -> list[str]:
    """Deduplicated, sorted permit set for the work types (JS-parity core)."""
    if not work_types:
        return []
    seen: set[str] = set()
    for wt in work_types:
        seen.update(_WORK_TYPE_TO_PERMITS.get(wt, ()))
    return sorted(seen)


def _sequenced(permits: list[str]) -> list[str]:
    """Order the permits by pull rank; unknown permits sort last, then a-z."""
    return sorted(permits, key=lambda p: (_SEQUENCE_RANK.get(p, 99), p))


def _fees(permits: list[str]) -> tuple[dict[str, int], int]:
    """Per-permit fee estimate and total for the permits that carry one."""
    breakdown = {p: _BASE_FEES[p] for p in permits if p in _BASE_FEES}
    return breakdown, sum(breakdown.values())


def _templated_note(sequence: list[str], municipality: str | None) -> str:
    """Deterministic fallback sequencing note (no model)."""
    where = f" in {municipality}" if municipality else ""
    if not sequence:
        return f"No permits appear required for this scope{where} (cosmetic work)."
    return f"Pull permits{where} in this order: {' → '.join(sequence)}."


def _llm_note(sequence: list[str], context: dict[str, Any], client: Any | None) -> str:
    """One short call for a project-specific sequencing rationale."""
    prompt = (
        f"Project municipality: {context.get('municipality')}\n"
        f"Work types: {', '.join(context.get('work_types') or [])}\n"
        f"Permit pull order: {' → '.join(sequence) or 'none'}\n"
        "In two sentences, explain the sequencing to a homeowner. No fees, no legalese."
    )
    result = run_agent(
        AGENT_NAME,
        system="You explain permit sequencing plainly. Be brief and concrete.",
        messages=[{"role": "user", "content": prompt}],
        tier=Tier.CHEAP,
        effort="low",
        max_tokens=256,
        temperature=0.0,
        input_parts=(context.get("municipality"), tuple(sequence)),
        client=client,
    )
    return (result.text or "").strip()


def plan_permits(
    context: dict[str, Any],
    *,
    use_llm: bool = True,
    client: Any | None = None,
) -> PermitStrategy:
    """Build the permit set, pull order, and fee estimate for a project.

    The set/order/fees are deterministic; only the ``notes`` string may come
    from a model, and it degrades to a templated note on failure or ``use_llm``
    off. Never raises.
    """
    permits = recommend_permits(context.get("work_types"))
    sequence = _sequenced(permits)
    breakdown, total = _fees(permits)
    note = _templated_note(sequence, context.get("municipality"))
    if use_llm and sequence:
        try:
            llm = _llm_note(sequence, context, client)
            if llm:
                note = llm
        except Exception as exc:  # notes are advisory, never a blocker
            log.warning("permit sequencing note failed, using template: %s", exc)
    return PermitStrategy(
        permits=permits,
        sequence=sequence,
        fee_breakdown=breakdown,
        estimated_fees_usd=total,
        notes=note,
    )
