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
- the latest **LangSmith** experiment per dataset (``evaluation/langsmith_eval.py``)
  — advisory-only metrics from a fixed offline eval set, not this window's live
  traffic. See ``Check.gates`` below.

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
from typing import Any

from db import client as db_client
from evaluation import eval_guard

log = logging.getLogger(__name__)

AGENT_NAME = "evaluator"
_LEVELS = ("L0", "L1", "L2", "L3")


@dataclass(frozen=True)
class Check:
    """One metric-contract clause: a metric, a comparator, and a threshold.

    ``gates`` controls whether a failing check can actually breach an agent's
    contract (affecting ``AgentReport.passed`` and, with ``apply=True``, filing
    an action item + demoting autonomy) or is advisory-only — reported every
    run, never enforced. Every check here defaulted to gating before LangSmith
    metrics existed; the LangSmith-derived checks below default to
    ``gates=False`` since they measure a fixed offline dataset, not live
    traffic, and haven't earned trust yet. Promote a specific agent's check to
    ``gates=True`` once you're confident in it — that's the per-agent middle
    ground between "gate everything" and "gate nothing."
    """

    metric: str
    op: str  # 'gte' | 'lte'
    threshold: float
    label: str
    gates: bool = True

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
# LangSmith-derived checks (gates=False) measure the latest experiment run
# against a fixed dataset (evaluation/langsmith_datasets/*.json) — see
# _latest_langsmith_metrics()'s docstring for the "latest ≠ deployed" caveat
# these inherit from the same trap already found in RAGAs' latest-export
# lookup (STATE.md punch #3c). Thresholds are starting points mirroring the
# RAGAs faithfulness floor, not calibrated from real data yet.
CONTRACTS: dict[str, tuple[Check, ...]] = {
    "answer_generator": (
        Check("faithfulness", "gte", 0.85, "RAGAs faithfulness ≥ 0.85"),
        Check("langsmith_hallucination_judge", "gte", 0.85,
              "LangSmith hallucination-judge pass rate ≥ 0.85", gates=False),
        Check("langsmith_citation_precision", "gte", 0.80,
              "LangSmith citation precision ≥ 0.80", gates=False),
        Check("langsmith_citation_recall", "gte", 0.80,
              "LangSmith citation recall ≥ 0.80", gates=False),
    ),
    "prompt_router": (Check("deterministic_rate", "gte", 1.0, "always deterministic (no LLM)"),),
    "manager": (
        # project_isolation_regression in langsmith_eval.py. Attributed to the
        # Manager (not a "retrieval" agent name) because retrieval runs via
        # ManagerDeps.retrieve, not a registry-resolved named agent, and the
        # Manager owns the plan that includes it. Strongest candidate for
        # gates=True promotion once the seed fixture is live and this has run
        # clean a few times — a leak here is a real security regression, not
        # a fuzzy quality signal.
        Check("langsmith_project_isolation", "gte", 1.0,
              "LangSmith project-isolation pass rate ≥ 1.0 (any leak breaches)",
              gates=False),
    ),
}


@dataclass
class AgentReport:
    """One agent's metrics + any contract breaches/advisories this window."""

    agent: str
    metrics: dict[str, float]
    breaches: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    demoted_to: str | None = None

    @property
    def passed(self) -> bool:
        """True when no *gating* contract clause was breached. Advisories never
        affect this — see Check.gates."""
        return not self.breaches


def _latest_faithfulness(results_dir: Path | None) -> float | None:
    """Avg faithfulness from the most recent RAGAs export, or None if absent."""
    try:
        path = eval_guard._latest_ragas_export(results_dir or eval_guard.DEFAULT_RESULTS_DIR)
        return eval_guard._extract_avg_faithfulness(eval_guard._load_payload(path))
    except Exception as exc:  # a missing/blank results dir must not break the eval
        log.warning("could not read RAGAs faithfulness: %s", exc)
        return None


# (dataset_name, evaluator key in evaluation/langsmith_eval.py::ALL_EVALUATORS,
# metric name reported here, agent it's attributed to). See CONTRACTS above
# for the reasoning behind each attribution.
_LANGSMITH_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("permit_rag_eval_v1", "hallucination_judge", "langsmith_hallucination_judge", "answer_generator"),
    ("permit_rag_eval_v1", "citation_precision", "langsmith_citation_precision", "answer_generator"),
    ("permit_rag_eval_v1", "citation_recall", "langsmith_citation_recall", "answer_generator"),
    ("permit_rag_security_v1", "project_isolation", "langsmith_project_isolation", "manager"),
)


def _experiment_metadata(project: Any) -> dict[str, Any]:
    """Best-effort read of an experiment's tagged metadata across SDK versions."""
    for attr in ("metadata", "extra"):
        value = getattr(project, attr, None)
        if isinstance(value, dict):
            nested = value.get("metadata")
            if isinstance(nested, dict):
                return nested
            if attr == "metadata":
                return value
    return {}


def _latest_experiment(dataset_name: str) -> Any | None:
    """The most recent experiment (LangSmith project) run against a dataset, or
    None if LangSmith isn't configured/reachable or nothing has run yet."""
    try:
        from langsmith import Client

        client = Client()
        projects = list(client.list_projects(reference_dataset_name=dataset_name))
        if not projects:
            return None
        return max(projects, key=lambda p: p.start_time or datetime.min)
    except Exception as exc:  # a LangSmith outage must not break the Evaluator
        log.warning("LangSmith experiment lookup failed for dataset %r: %s", dataset_name, exc)
        return None


def _langsmith_stats_for_dataset(
    dataset: str, deployed_prompt_version: str, deployed_library_version: str
) -> dict[str, float] | None:
    """Feedback-key means for the latest *version-matched* experiment on
    ``dataset``, or None if there's no experiment, LangSmith is unreachable,
    or the latest experiment's tagged version doesn't match what's deployed."""
    experiment = _latest_experiment(dataset)
    if experiment is None:
        return None
    meta = _experiment_metadata(experiment)
    exp_prompt_version = meta.get("prompt_version")
    exp_library_version = meta.get("library_version")
    # Fail closed: a *missing* tag means "can't verify this matches deployed,"
    # not "no claim was made, so let it through." Confirmed empirically
    # (2026-08-06) why this matters -- the real permit_rag_eval_v1 experiment
    # on record predates library_version tagging entirely (added this
    # session), so exp_library_version is None for it; the original
    # "None means no claim, don't penalize" logic let its numbers through as
    # if fresh, silently reporting a 07-22 baseline's scores as current.
    stale = (
        exp_prompt_version != deployed_prompt_version
        or exp_library_version != deployed_library_version
    )
    if stale:
        log.warning(
            "LangSmith experiment %r for %r is stale (ran at "
            "prompt_version=%r/library_version=%r, deployed is %r/%r) -- "
            "skipping its metrics rather than reporting a possibly-wrong number",
            getattr(experiment, "name", "?"), dataset,
            exp_prompt_version, exp_library_version,
            deployed_prompt_version, deployed_library_version,
        )
        return None
    return _aggregate_feedback(experiment)


def _aggregate_feedback(experiment: Any) -> dict[str, float]:
    """
    Mean score per feedback key across every root run in an experiment.

    Confirmed empirically (2026-08-06, against a freshly-completed real
    experiment, not a stale one): ``Project.feedback_stats`` is *not*
    populated for experiments run via ``langsmith.evaluation.evaluate()`` --
    both ``list_projects()`` and a forced-fresh ``read_project()`` returned
    ``None``, not even an empty dict. The real per-run scores are only
    reachable via ``list_feedback(run_ids=...)``, so aggregate by hand
    instead of trusting the higher-level attribute the first version of this
    function assumed worked.
    """
    from langsmith import Client

    client = Client()
    runs = list(client.list_runs(project_id=experiment.id, execution_order=1))
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for run in runs:
        for fb in client.list_feedback(run_ids=[run.id]):
            if fb.score is None:
                continue
            sums[fb.key] = sums.get(fb.key, 0.0) + float(fb.score)
            counts[fb.key] = counts.get(fb.key, 0) + 1
    return {key: total / counts[key] for key, total in sums.items()}


def _latest_langsmith_metrics() -> dict[str, dict[str, float]]:
    """
    Per-agent advisory metrics from the latest LangSmith experiment per dataset
    (``_LANGSMITH_SOURCES``). Report-only until a check is promoted to
    ``gates=True`` (see ``Check.gates``) -- these measure a fixed offline
    dataset, not this window's live traffic.

    Guards the "latest ≠ deployed" trap already found and documented for
    RAGAs' ``_latest_ragas_export()`` (STATE.md punch #3c): an experiment is
    only trusted if its tagged ``prompt_version``/``library_version``
    metadata (set by ``langsmith_eval.py``'s CLI) matches what's currently
    deployed. A stale or reverted experiment is skipped entirely rather than
    silently reported -- for an advisory metric, saying nothing is safer than
    saying something wrong.
    """
    from rag.generator import PROMPT_VERSION
    from rag.prompts import library_version as current_library_version

    deployed_prompt_version = PROMPT_VERSION
    deployed_library_version = current_library_version()

    by_dataset: dict[str, dict[str, float] | None] = {}
    result: dict[str, dict[str, float]] = {}
    for dataset, eval_key, metric_name, agent in _LANGSMITH_SOURCES:
        if dataset not in by_dataset:
            # Defense in depth: _latest_experiment already guards its own
            # LangSmith calls, but nothing here should ever be able to take
            # the whole Evaluator down -- an unexpected error anywhere in
            # this dataset's lookup just means no advisory metrics from it.
            try:
                by_dataset[dataset] = _langsmith_stats_for_dataset(
                    dataset, deployed_prompt_version, deployed_library_version
                )
            except Exception as exc:
                log.warning("LangSmith metric lookup failed for dataset %r: %s", dataset, exc)
                by_dataset[dataset] = None
        stats = by_dataset[dataset]
        if not stats or eval_key not in stats:
            continue
        result.setdefault(agent, {})[metric_name] = stats[eval_key]
    return result


def compute_metrics(
    *, since: datetime, results_dir: Path | None = None
) -> dict[str, dict[str, float]]:
    """Merge the scorecard, correction rate, RAGAs faithfulness, and LangSmith
    advisory metrics into per-agent metrics."""
    scorecard = {r["agent_name"]: r for r in db_client.agent_scorecard(since=since)}
    corrections = {r["agent_name"]: r for r in db_client.correction_rate_by_agent(since=since)}
    faithfulness = _latest_faithfulness(results_dir)
    langsmith_metrics = _latest_langsmith_metrics()

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
        m.update(langsmith_metrics.get(agent, {}))
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
    """
    Score every agent against its contract. ``apply`` files items + demotes.

    Only gating checks (``Check.gates=True``) can breach and trigger
    ``apply``'s side effects. Non-gating checks are always evaluated and
    reported as ``AgentReport.advisories`` -- visible in every run, never
    filed as an action item, never a factor in ``passed`` or demotion.
    """
    metrics = compute_metrics(since=since, results_dir=results_dir)
    reports: list[AgentReport] = []
    for agent, m in sorted(metrics.items()):
        gating: list[str] = []
        advisory: list[str] = []
        for chk in _checks_for(agent):
            if chk.passes(m.get(chk.metric)) is False:
                line = f"{chk.label} (got {m[chk.metric]:.3f})"
                (gating if chk.gates else advisory).append(line)
        report = AgentReport(agent=agent, metrics=m, breaches=gating, advisories=advisory)
        if gating and apply:
            db_client.upsert_action_item(
                source_agent=AGENT_NAME,
                kind="metric_contract_breach",
                title=f"{agent}: metric contract breached",
                severity="high",
                entity_type="agent",
                entity_id=agent,
                evidence={
                    "breaches": gating,
                    "advisories": advisory,
                    "metrics": {k: round(v, 4) for k, v in m.items()},
                },
                proposed_action="Review recent traces; the agent was auto-demoted one autonomy level.",
            )
            report.demoted_to = _demote_one_level(agent)
        reports.append(report)
    return reports
