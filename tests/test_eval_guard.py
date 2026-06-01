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
