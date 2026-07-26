"""
evaluation/perf_review.py — Performance Review (agent #24)
==========================================================
Phase 5. Turns a user's thumbs-down (the answer-level feedback loop, migration
033) into an *attributed* correction: which agent/step is responsible for the
bad answer? Attribution is genuinely hard — a wrong answer can come from bad
chunks (Retrieval), a hallucination (Answer Generator), a wrong persona fragment
(Prompt Router), or a mislabeled document that made the retrieval filter exclude
the right source. This agent reads ``(feedback, full run trace)`` and proposes a
structured correction with an attributed agent, failure mode, evidence, and
confidence (docs/agent_architecture.md "Performance Review agent").

**Deterministic first, LLM only where it must be.** Two failure classes are
attributable with zero model spend from the trace alone:

1. A step recorded ``status='error'`` (or the run ``outcome='error'``) — attribute
   to that agent, no LLM.
2. A grounding abstain (``model='abstained'``, no generation) — the system chose
   not to answer; a down-vote here is a retrieval-coverage gap, attribute to the
   retriever.

Everything else is a quality judgement over the trace → one structured
``run_agent`` call on the top tier (low volume, batched — the arch budgets
~$0.03 per thumbs-down).

**Governance: never silent blame.** Every review writes an *unconfirmed*
``agent_corrections`` row; a superadmin confirms it in the dashboard, which is
what closes the loop into training data. Below the confidence floor the row
carries no ``attributed_agent`` (a human assigns it) — the arch's low-confidence
→ human-confirmation rule. This module is the writer of that row; it is invoked
by ``scripts/review_feedback.py`` (batched), never on the query hot path.

Import boundary: evaluation/ → rag/, db/, standard library only (AGENTS.md).
Every model call goes through ``run_agent`` — no inline Anthropic client here.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from db import client as db_client
from rag.agent_runtime import Tier, run_agent

log = logging.getLogger(__name__)

AGENT_NAME = "performance_review"

# Below this the model's attribution is a hint, not a verdict: the correction is
# still written (for the queue) but with no attributed_agent — a human assigns
# blame. Mirrors the autonomy split (high-confidence L2, low-confidence L0).
CONFIDENCE_FLOOR = 0.6

# Agents the reviewer is allowed to blame — the answer-path roster. Keeps the
# model from inventing a component and makes the metric contract measurable.
KNOWN_AGENTS: frozenset[str] = frozenset({
    "retriever",
    "answer_generator",
    "prompt_router",
    "guardrail",
    "manager",
    "media_curator",
})

_SYSTEM = (
    "You are the Performance Review agent for a permit-compliance RAG system. "
    "A user marked an answer unhelpful. Given the run trace (the ordered agent "
    "steps) and the user's comment, attribute the failure to exactly one agent "
    "and explain why, citing the step. Allowed agents: "
    + ", ".join(sorted(KNOWN_AGENTS))
    + ". If the trace does not justify blaming a specific agent, set "
    "attributed_agent to null and say so. Never invent an agent not listed. "
    "confidence is your certainty in the attribution, 0..1."
)


class Attribution(BaseModel):
    """The reviewer's structured verdict on one bad answer."""

    attributed_agent: str | None = Field(
        default=None,
        description="Responsible agent (one of the known agents), or null if unclear.",
    )
    failure_mode: str = Field(description="Short label, e.g. 'hallucination', 'bad_retrieval'.")
    evidence: str = Field(description="What in the trace points at this agent.")
    confidence: float = Field(ge=0.0, le=1.0, description="Certainty in the attribution.")
    rationale: str = Field(description="One or two sentences of reasoning.")


def _step_agents(steps: list[dict[str, Any]]) -> list[str]:
    """Agent names in a run's steps, in order (for the trace summary)."""
    return [str(s.get("agent_name", "")) for s in steps]


def _deterministic_attribution(
    run: dict[str, Any], steps: list[dict[str, Any]]
) -> Attribution | None:
    """Attribute the two zero-LLM failure classes; None means 'ask the model'."""
    errored = next((s for s in steps if s.get("status") == "error"), None)
    if errored is not None or run.get("outcome") == "error":
        agent = str(errored["agent_name"]) if errored else (str(run.get("entrypoint") or "manager"))
        return Attribution(
            attributed_agent=agent if agent in KNOWN_AGENTS else "manager",
            failure_mode="step_error",
            evidence=f"step '{agent}' recorded status=error: {(errored or run).get('error')!r}",
            confidence=0.9,
            rationale="A step failed outright; the error is attributable without a model.",
        )
    abstained = run.get("outcome") == "blocked" or any(
        s.get("model") == "abstained" for s in steps
    )
    if abstained:
        return Attribution(
            attributed_agent="retriever",
            failure_mode="grounding_abstain",
            evidence="run abstained on the grounding floor — no chunk cleared the threshold",
            confidence=0.65,
            rationale="A down-vote on an abstain is a retrieval-coverage gap, not generation.",
        )
    return None


def _trace_summary(run: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    """Compact, text-only trace digest — bounded, never carries chunk payloads."""
    lines = [
        f"run outcome={run.get('outcome')} intent={run.get('intent')} "
        f"persona={run.get('persona')} steps={len(steps)}",
    ]
    for s in steps:
        lines.append(
            f"- step {s.get('step_index')}: agent={s.get('agent_name')} "
            f"model={s.get('model') or 'deterministic'} status={s.get('status')} "
            f"tokens_out={s.get('tokens_out')} fragments={list(s.get('prompt_fragment_ids') or [])}"
        )
    return "\n".join(lines)


def attribute(
    run: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    comment: str | None = None,
    use_llm: bool = True,
    client: Any | None = None,
) -> Attribution:
    """Attribute a bad answer to an agent — deterministic first, else one call.

    ``use_llm=False`` returns a low-confidence unattributed result instead of
    paying for a model (the batch driver's ``--no-llm`` mode).
    """
    verdict = _deterministic_attribution(run, steps)
    if verdict is not None:
        return verdict
    if not use_llm:
        return Attribution(
            attributed_agent=None,
            failure_mode="unreviewed",
            evidence="deterministic checks found no clear cause; LLM review skipped",
            confidence=0.0,
            rationale="Left for human attribution (--no-llm).",
        )
    prompt = _trace_summary(run, steps)
    if comment:
        prompt += f"\n\nUser comment: {comment.strip()[:1000]}"
    result = run_agent(
        AGENT_NAME,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        tier=Tier.TOP,  # attribution is a hard judgement — opus per the cost table
        output_format=Attribution,
        max_tokens=1024,
        temperature=0.0,
        input_parts=(str(run.get("id")), _step_agents(steps)),
        client=client,
    )
    attr = result.parsed_output
    # Clamp a hallucinated agent name back to "unclear" so the metric stays honest.
    if attr.attributed_agent and attr.attributed_agent not in KNOWN_AGENTS:
        attr.attributed_agent = None
    return attr


def review_run(
    run_id: UUID,
    *,
    comment: str | None = None,
    created_by: UUID | None = None,
    use_llm: bool = True,
    client: Any | None = None,
) -> dict[str, Any] | None:
    """Review one down-voted run: attribute it and write an unconfirmed correction.

    Returns a summary dict, or None if the run does not exist. The correction is
    always ``confirmed=False`` — a human confirms attribution in the dashboard.
    Below the confidence floor the row carries no attributed_agent.
    """
    run = db_client.get_agent_run(run_id)
    if run is None:
        return None
    steps = db_client.list_agent_steps(run_id)
    attr = attribute(run, steps, comment=comment, use_llm=use_llm, client=client)

    confident = attr.confidence >= CONFIDENCE_FLOOR
    notes = f"[perf_review] {attr.failure_mode}: {attr.evidence} — {attr.rationale}"
    if comment:
        notes += f"\nuser: {comment.strip()[:500]}"
    row = db_client.insert_agent_correction(
        source="answer",
        run_id=run_id,
        attributed_agent=attr.attributed_agent if confident else None,
        attribution_confidence=round(attr.confidence, 2),
        severity="medium",
        notes=notes,
        confirmed=False,
        created_by=created_by,
    )
    return {
        "run_id": str(run_id),
        "attributed_agent": attr.attributed_agent if confident else None,
        "confidence": attr.confidence,
        "needs_human_attribution": not confident,
        "correction_id": str(row["id"]) if row else None,
    }
