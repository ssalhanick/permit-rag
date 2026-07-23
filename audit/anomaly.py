"""
audit/anomaly.py — turn trace statistics into action items
===========================================================
Reads the trace store and files an action item when an agent drifts. Output
goes to `agent_action_items`, not to logs, because logs do not get read --
an action item shows up in the superadmin queue with a severity and a
proposed action.

Deliberately statistics, not an LLM. Every check here is arithmetic over rows
audit/logger.py already wrote, which keeps the module inside the AGENTS.md
import boundary (audit/ -> db/, stdlib) and makes the alerting layer free to
run on a cron without a token budget.

Detectors:
  - faithfulness below the 0.85 AGENTS.md floor on a rolling window
  - cost or latency spike against an agent's own trailing baseline
  - cache-read collapse (the metric that is 0 today, pre-Prompt-Router)
  - error-rate spike
  - correction-rate rise, which also triggers autonomy demotion

Usage:
    py -m audit.anomaly --window-hours 24
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from db import client as db_client

log = logging.getLogger(__name__)

SOURCE_AGENT = "anomaly_detector"

# ── Thresholds ───────────────────────────────────────────────
# AGENTS.md: faithfulness must clear 0.85 before any customer demo.
FAITHFULNESS_FLOOR = 0.85
# Multiples of an agent's trailing baseline before it is considered a spike.
COST_SPIKE_MULTIPLE = 2.0
LATENCY_SPIKE_MULTIPLE = 2.0
ERROR_RATE_CEILING = 0.10
CORRECTION_RATE_CEILING = 0.20
# Below this share of calls reading cache, caching is effectively off.
CACHE_READ_FLOOR = 0.20
# Ignore agents with too few calls to say anything meaningful.
MIN_CALLS_FOR_SIGNAL = 20


@dataclass
class Finding:
    """One detected anomaly, ready to be filed as an action item."""

    agent_name: str
    kind: str
    severity: str
    title: str
    evidence: dict[str, Any]
    proposed_action: str


def _rate(numerator: float | None, denominator: float | None) -> float:
    """Safe ratio; 0.0 when the denominator is absent or zero."""
    if not denominator:
        return 0.0
    return float(numerator or 0.0) / float(denominator)


def detect_error_spikes(scorecard: list[dict[str, Any]]) -> list[Finding]:
    """Flag agents erroring more often than ERROR_RATE_CEILING."""
    findings: list[Finding] = []
    for row in scorecard:
        calls = int(row.get("calls") or 0)
        error_rate = float(row.get("error_rate") or 0.0)
        if calls < MIN_CALLS_FOR_SIGNAL or error_rate <= ERROR_RATE_CEILING:
            continue
        findings.append(
            Finding(
                agent_name=row["agent_name"],
                kind="error_rate_spike",
                severity="high" if error_rate > 0.25 else "medium",
                title=f"{row['agent_name']} error rate {error_rate:.0%} over {calls} calls",
                evidence={"calls": calls, "error_rate": error_rate},
                proposed_action="Inspect recent errored steps in the trace explorer.",
            )
        )
    return findings


def detect_cache_collapse(scorecard: list[dict[str, Any]]) -> list[Finding]:
    """
    Flag agents whose cached-token share has collapsed.

    A silent invalidator -- a timestamp in a system prompt, an unsorted dict,
    a per-project string in the cached prefix -- produces exactly this and no
    error. Expected to fire on every project-scoped agent until the Prompt
    Router lands, which is the point: it makes the regression visible.
    """
    findings: list[Finding] = []
    for row in scorecard:
        calls = int(row.get("calls") or 0)
        tokens = float(row.get("tokens") or 0.0)
        cache_read = float(row.get("tokens_cache_read") or 0.0)
        if calls < MIN_CALLS_FOR_SIGNAL or tokens <= 0:
            continue
        share = _rate(cache_read, tokens)
        if share >= CACHE_READ_FLOOR:
            continue
        findings.append(
            Finding(
                agent_name=row["agent_name"],
                kind="cache_read_collapse",
                severity="medium",
                title=f"{row['agent_name']} cache-read share {share:.0%}",
                evidence={
                    "calls": calls,
                    "tokens": tokens,
                    "tokens_cache_read": cache_read,
                    "cache_read_share": share,
                },
                proposed_action=(
                    "Audit the cached prefix for volatile content, and confirm it "
                    "clears the 4096-token minimum on Haiku/Opus (2048 on Sonnet)."
                ),
            )
        )
    return findings


def detect_baseline_drift(
    current: list[dict[str, Any]], baseline: list[dict[str, Any]]
) -> list[Finding]:
    """
    Compare a window against a trailing baseline for cost and latency spikes.

    Per-agent rather than global: a Manager that got more expensive is a very
    different problem from a Generator that did, and a global average hides
    both.
    """
    base = {row["agent_name"]: row for row in baseline}
    findings: list[Finding] = []
    for row in current:
        agent = row["agent_name"]
        prior = base.get(agent)
        if not prior or int(row.get("calls") or 0) < MIN_CALLS_FOR_SIGNAL:
            continue

        now_cost = _rate(row.get("cost_usd"), row.get("calls"))
        was_cost = _rate(prior.get("cost_usd"), prior.get("calls"))
        if was_cost > 0 and now_cost > was_cost * COST_SPIKE_MULTIPLE:
            findings.append(
                Finding(
                    agent_name=agent,
                    kind="cost_spike",
                    severity="high",
                    title=f"{agent} cost/call {now_cost:.4f} vs baseline {was_cost:.4f}",
                    evidence={"cost_per_call": now_cost, "baseline": was_cost},
                    proposed_action="Check for a model-tier change or context growth.",
                )
            )

        now_p95 = float(row.get("p95_latency_ms") or 0.0)
        was_p95 = float(prior.get("p95_latency_ms") or 0.0)
        if was_p95 > 0 and now_p95 > was_p95 * LATENCY_SPIKE_MULTIPLE:
            findings.append(
                Finding(
                    agent_name=agent,
                    kind="latency_spike",
                    severity="medium",
                    title=f"{agent} p95 {now_p95:.0f}ms vs baseline {was_p95:.0f}ms",
                    evidence={"p95_latency_ms": now_p95, "baseline": was_p95},
                    proposed_action="Check ReAct iteration counts and retry behaviour.",
                )
            )
    return findings


def detect_correction_spikes(
    scorecard: list[dict[str, Any]], corrections: list[dict[str, Any]]
) -> list[Finding]:
    """
    Flag agents drawing human corrections on more than a fifth of their calls.

    This is the signal that should also demote autonomy: an agent being
    corrected this often has not earned the level it is running at.
    """
    calls_by_agent = {r["agent_name"]: int(r.get("calls") or 0) for r in scorecard}
    findings: list[Finding] = []
    for row in corrections:
        agent = row["agent_name"]
        calls = calls_by_agent.get(agent, 0)
        confirmed = int(row.get("confirmed_corrections") or 0)
        if calls < MIN_CALLS_FOR_SIGNAL:
            continue
        rate = _rate(confirmed, calls)
        if rate <= CORRECTION_RATE_CEILING:
            continue
        findings.append(
            Finding(
                agent_name=agent,
                kind="correction_rate_spike",
                severity="high",
                title=f"{agent} corrected on {rate:.0%} of calls",
                evidence={"calls": calls, "confirmed_corrections": confirmed,
                          "correction_rate": rate},
                proposed_action=(
                    "Review attributed failures; demote this agent one autonomy "
                    "level until the rate recovers."
                ),
            )
        )
    return findings


def check_faithfulness(score: float | None, *, sample_size: int) -> list[Finding]:
    """
    Flag a faithfulness score below the AGENTS.md floor.

    Score comes from the caller (evaluation/ragas_eval.py) rather than being
    computed here -- this module stays free of rag/ and evaluation/ imports.
    """
    if score is None or score >= FAITHFULNESS_FLOOR:
        return []
    return [
        Finding(
            agent_name="answer_generator",
            kind="faithfulness_below_floor",
            severity="critical",
            title=f"Faithfulness {score:.3f} below the {FAITHFULNESS_FLOOR} floor",
            evidence={"faithfulness": score, "sample_size": sample_size,
                      "floor": FAITHFULNESS_FLOOR},
            proposed_action=(
                "Block customer demos until resolved (AGENTS.md). Re-run RAGAs and "
                "compare prompt fragment versions against the last passing run."
            ),
        )
    ]


def file_findings(findings: list[Finding]) -> int:
    """
    Write findings to the action queue. Returns the number filed.

    Deduped by the open-item unique index, so a nightly sweep refreshes an
    existing item rather than stacking duplicates.
    """
    filed = 0
    for finding in findings:
        try:
            db_client.upsert_action_item(
                source_agent=SOURCE_AGENT,
                kind=finding.kind,
                title=finding.title,
                severity=finding.severity,
                entity_type="agent",
                entity_id=finding.agent_name,
                evidence=finding.evidence,
                proposed_action=finding.proposed_action,
            )
            filed += 1
        except Exception as exc:
            log.warning("Could not file action item %s: %s", finding.kind, exc)
    return filed


def run_sweep(*, window_hours: int = 24, baseline_days: int = 14) -> list[Finding]:
    """Run every detector over a window and file what it finds."""
    now = datetime.now(UTC)
    window_start = now - timedelta(hours=window_hours)
    baseline_start = now - timedelta(days=baseline_days)

    current = db_client.agent_scorecard(since=window_start)
    baseline = db_client.agent_scorecard(since=baseline_start)
    corrections = db_client.correction_rate_by_agent(since=window_start)

    findings = [
        *detect_error_spikes(current),
        *detect_cache_collapse(current),
        *detect_baseline_drift(current, baseline),
        *detect_correction_spikes(current, corrections),
    ]
    filed = file_findings(findings)
    log.info("Anomaly sweep: %d findings, %d filed", len(findings), filed)
    return findings


def main() -> None:
    """CLI entry point for the scheduled sweep."""
    parser = argparse.ArgumentParser(description="Scan agent traces for anomalies.")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--baseline-days", type=int, default=14)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    findings = run_sweep(
        window_hours=args.window_hours, baseline_days=args.baseline_days
    )
    for finding in findings:
        print(f"[{finding.severity}] {finding.agent_name}: {finding.title}")
    if not findings:
        print("No anomalies detected.")


if __name__ == "__main__":
    main()
