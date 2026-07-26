"""
evaluation/agent_eval.py — Evaluator (agent #23)
================================================
Phase 5. Scores each agent against its *metric contract* — the thresholds in
docs/agent_architecture.md "Per-agent metric contracts" — reading the trace
store the Phase-0 telemetry already fills. The contract breach is the mechanism
the whole autonomy design hangs on: **a breach auto-demotes the agent one level
and files an action item** (arch "Graduated autonomy — earned, not guessed"),
so an agent that starts regressing loses trust until a human reviews.

Sources, all deterministic (no model spend — the Evaluator judges, it does not
generate):
- ``agent_scorecard`` — calls, deterministic-hit-rate, error rate, latency.
- ``correction_rate_by_agent`` — confirmed corrections (the Performance Review
  #24 output + the metadata-review corrections) per agent.
- the latest **RAGAs** export — faithfulness for the answer generator (the arch
  hook: the multi-sample live baseline belongs to this agent; STATE punch #3).

Propose-first, like the rest of the system: ``evaluate()`` reads and reports;
only ``apply=True`` writes (files the action item + demotes). Driven by
``scripts/run_agent_eval.py`` (machine B — needs trace volume).

Import boundary: evaluation/ → rag/, db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from db import client as db_client
from evaluation import eval_guard

log = logging.getLogger(__name__)

AGENT_NAME = "evaluator"
_LEVELS = ("L0", "L1", "L2", "L3")


@dataclass(frozen=True)
class Check:
    """One metric-contract clause: a metric, a comparator, and a threshold."""

    metric: str
    op: str  # 'gte' | 'lte'
    threshold: float
    label: str

    def passes(self, value: float | None) -> bool | None:
        """True/False against the threshold; None when the metric is absent."""
        if value is None:
            return None  # not measurable this window — not a breach
        return value >= self.threshold if self.op == "gte" else value <= self.threshold


# Applied to every agent (arch "All" row).
GLOBAL_CHECKS: tuple[Check, ...] = (
    Check("correction_rate", "lte", 0.20, "confirmed-correction rate ≤ 0.20"),
    Check("error_rate", "lte", 0.05, "step error rate ≤ 0.05"),
)
# Agent-specific contracts (the measurable subset of the arch table today).
CONTRACTS: dict[str, tuple[Check, ...]] = {
    "answer_generator": (Check("faithfulness", "gte", 0.85, "RAGAs faithfulness ≥ 0.85"),),
    "prompt_router": (Check("deterministic_rate", "gte", 1.0, "always deterministic (no LLM)"),),
}


@dataclass
class AgentReport:
    """One agent's metrics + any contract breaches this window."""

    agent: str
    metrics: dict[str, float]
    breaches: list[str] = field(default_factory=list)
    demoted_to: str | None = None

    @property
    def passed(self) -> bool:
        """True when no contract clause was breached."""
        return not self.breaches


def _latest_faithfulness(results_dir: Path | None) -> float | None:
    """Avg faithfulness from the most recent RAGAs export, or None if absent."""
    try:
        path = eval_guard._latest_ragas_export(results_dir or eval_guard.DEFAULT_RESULTS_DIR)
        return eval_guard._extract_avg_faithfulness(eval_guard._load_payload(path))
    except Exception as exc:  # a missing/blank results dir must not break the eval
        log.warning("could not read RAGAs faithfulness: %s", exc)
        return None


def compute_metrics(
    *, since: datetime, results_dir: Path | None = None
) -> dict[str, dict[str, float]]:
    """Merge the scorecard, correction rate, and faithfulness into per-agent metrics."""
    scorecard = {r["agent_name"]: r for r in db_client.agent_scorecard(since=since)}
    corrections = {r["agent_name"]: r for r in db_client.correction_rate_by_agent(since=since)}
    faithfulness = _latest_faithfulness(results_dir)

    metrics: dict[str, dict[str, float]] = {}
    for agent, row in scorecard.items():
        calls = float(row.get("calls") or 0)
        confirmed = float((corrections.get(agent) or {}).get("confirmed_corrections") or 0)
        m = {
            "calls": calls,
            "deterministic_rate": float(row.get("deterministic_rate") or 0.0),
            "error_rate": float(row.get("error_rate") or 0.0),
            "correction_rate": (confirmed / calls) if calls else 0.0,
            "avg_latency_ms": float(row.get("avg_latency_ms") or 0.0),
        }
        if agent == "answer_generator" and faithfulness is not None:
            m["faithfulness"] = faithfulness
        metrics[agent] = m
    return metrics


def _checks_for(agent: str) -> tuple[Check, ...]:
    """The global contract plus any agent-specific clauses."""
    return GLOBAL_CHECKS + CONTRACTS.get(agent, ())


def _demote_one_level(agent: str, scope: str = "default") -> str | None:
    """Drop an agent one autonomy level (clamped at L0). None if not applicable."""
    row = db_client.get_agent_autonomy(agent, scope)
    if not row:
        return None
    current = row.get("current_level")
    if current not in _LEVELS or current == "L0":
        return None
    lower = _LEVELS[_LEVELS.index(current) - 1]
    updated = db_client.set_agent_autonomy(agent, scope, current_level=lower)
    return lower if updated else None


def evaluate(
    *, since: datetime, apply: bool = False, results_dir: Path | None = None
) -> list[AgentReport]:
    """Score every agent against its contract. ``apply`` files items + demotes."""
    metrics = compute_metrics(since=since, results_dir=results_dir)
    reports: list[AgentReport] = []
    for agent, m in sorted(metrics.items()):
        breaches = [
            f"{chk.label} (got {m[chk.metric]:.3f})"
            for chk in _checks_for(agent)
            if chk.passes(m.get(chk.metric)) is False
        ]
        report = AgentReport(agent=agent, metrics=m, breaches=breaches)
        if breaches and apply:
            db_client.upsert_action_item(
                source_agent=AGENT_NAME,
                kind="metric_contract_breach",
                title=f"{agent}: metric contract breached",
                severity="high",
                entity_type="agent",
                entity_id=agent,
                evidence={"breaches": breaches, "metrics": {k: round(v, 4) for k, v in m.items()}},
                proposed_action="Review recent traces; the agent was auto-demoted one autonomy level.",
            )
            report.demoted_to = _demote_one_level(agent)
        reports.append(report)
    return reports
