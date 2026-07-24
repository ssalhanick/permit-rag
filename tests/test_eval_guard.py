"""
tests/test_eval_guard.py — Regression guard tests for eval exports.
"""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.eval_guard import run_guard


def _write_payload(
    path: Path,
    *,
    avg_faithfulness: float | None,
    q1_faithfulness: float,
) -> None:
    """Write a minimal RAGAs-like payload for guard testing."""
    payload: dict = {
        "results": [
            {"faithfulness": 0.80},
            {"faithfulness": q1_faithfulness},
            {"faithfulness": 0.90},
        ]
    }
    if avg_faithfulness is not None:
        payload["run_metrics"] = {"avg_faithfulness": avg_faithfulness}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_run_guard_passes_with_healthy_metrics(tmp_path: Path) -> None:
    """Guard should pass when avg and q1 drift are within thresholds."""
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_payload(baseline, avg_faithfulness=None, q1_faithfulness=0.60)
    _write_payload(candidate, avg_faithfulness=0.89, q1_faithfulness=0.55)

    passed, _messages = run_guard(
        candidate_path=candidate,
        baseline_path=baseline,
        min_avg_faithfulness=0.85,
        q1_index=1,
        max_q1_drop=0.10,
    )

    assert passed is True


def test_run_guard_fails_when_avg_faithfulness_drops(tmp_path: Path) -> None:
    """Guard should fail when candidate avg faithfulness is below threshold."""
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_payload(baseline, avg_faithfulness=None, q1_faithfulness=0.60)
    _write_payload(candidate, avg_faithfulness=0.84, q1_faithfulness=0.55)

    passed, messages = run_guard(
        candidate_path=candidate,
        baseline_path=baseline,
        min_avg_faithfulness=0.85,
        q1_index=1,
        max_q1_drop=0.10,
    )

    assert passed is False
    assert any("avg_faithfulness_below_min" in line for line in messages)


def test_run_guard_fails_when_q1_drop_exceeds_limit(tmp_path: Path) -> None:
    """Guard should fail when q1 faithfulness drops by more than allowed."""
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_payload(baseline, avg_faithfulness=None, q1_faithfulness=0.60)
    _write_payload(candidate, avg_faithfulness=0.90, q1_faithfulness=0.49)

    passed, messages = run_guard(
        candidate_path=candidate,
        baseline_path=baseline,
        min_avg_faithfulness=0.85,
        q1_index=1,
        max_q1_drop=0.10,
    )

    assert passed is False
    assert any("q1_faithfulness_drop_exceeded" in line for line in messages)


def test_run_guard_refuses_to_compare_a_file_to_itself(tmp_path: Path) -> None:
    """
    Same candidate and baseline must fail loudly rather than pass silently.

    `ragas_eval` writes a results file only with --export. Without it no new
    file appears, `_latest_ragas_export` falls back to the newest existing one
    -- often the baseline itself -- and the guard compared it to itself,
    reporting drop=0.000 and PASS. A green gate carrying no information is
    worse than a red one, especially right before a prod push.
    """
    export = tmp_path / "ragas_20260721_183712.json"
    _write_payload(export, avg_faithfulness=0.90, q1_faithfulness=0.60)

    passed, messages = run_guard(
        candidate_path=export,
        baseline_path=export,
        min_avg_faithfulness=0.85,
        q1_index=1,
        max_q1_drop=0.10,
    )

    assert passed is False
    assert any("same file" in line for line in messages)
    assert any("--export" in line for line in messages)


def test_run_guard_warns_when_candidate_predates_baseline(tmp_path: Path) -> None:
    """An auto-selected candidate older than the baseline signals a missed export."""
    import os

    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_payload(baseline, avg_faithfulness=None, q1_faithfulness=0.60)
    _write_payload(candidate, avg_faithfulness=0.90, q1_faithfulness=0.58)
    os.utime(candidate, (1_600_000_000, 1_600_000_000))  # older than baseline

    passed, messages = run_guard(
        candidate_path=candidate,
        baseline_path=baseline,
        min_avg_faithfulness=0.85,
        q1_index=1,
        max_q1_drop=0.10,
    )

    assert passed is True  # a warning, not a failure
    assert any("older than the baseline" in line for line in messages)


def test_run_guard_credits_an_improvement(tmp_path: Path) -> None:
    """
    A negative drop (candidate above baseline) is an improvement, and passes.

    This is the post-chunk-leakage-fix outcome: dropping reranker-rejected
    chunks raised q1 faithfulness, so baseline - candidate is negative.
    """
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_payload(baseline, avg_faithfulness=None, q1_faithfulness=0.60)
    _write_payload(candidate, avg_faithfulness=0.91, q1_faithfulness=0.788)

    passed, messages = run_guard(
        candidate_path=candidate,
        baseline_path=baseline,
        min_avg_faithfulness=0.85,
        q1_index=1,
        max_q1_drop=0.10,
    )

    assert passed is True
    assert any("drop=-0.188" in line for line in messages)
