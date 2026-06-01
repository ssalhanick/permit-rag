"""
evaluation/eval_guard.py — Lightweight regression guard for RAGAs exports.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_BASELINE_PATH = Path("evaluation/results/ragas_20260531_122639.json")
DEFAULT_RESULTS_DIR = Path("evaluation/results")
DEFAULT_MIN_AVG_FAITHFULNESS = 0.85
DEFAULT_Q1_INDEX = 1
DEFAULT_MAX_Q1_DROP = 0.10


def _load_payload(path: Path) -> dict[str, Any]:
    """Load and parse a RAGAs JSON export payload from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_avg_faithfulness(payload: dict[str, Any]) -> float:
    """Return avg faithfulness from run_metrics or derive it from results."""
    run_metrics = payload.get("run_metrics")
    if isinstance(run_metrics, dict):
        value = run_metrics.get("avg_faithfulness")
        if isinstance(value, (int, float)):
            return float(value)

    results = payload.get("results", [])
    faith_values = [
        float(row["faithfulness"])
        for row in results
        if isinstance(row, dict) and isinstance(row.get("faithfulness"), (int, float))
    ]
    if not faith_values:
        raise ValueError("No faithfulness values found in payload.")
    return sum(faith_values) / len(faith_values)


def _extract_query_faithfulness(payload: dict[str, Any], query_index: int) -> float:
    """Return faithfulness for a specific query index from results[]."""
    results = payload.get("results", [])
    if not isinstance(results, list) or query_index >= len(results):
        raise ValueError(f"Missing query index {query_index} in results.")
    row = results[query_index]
    value = row.get("faithfulness") if isinstance(row, dict) else None
    if not isinstance(value, (int, float)):
        raise ValueError(f"Missing numeric faithfulness at query index {query_index}.")
    return float(value)


def _latest_ragas_export(results_dir: Path) -> Path:
    """Return the most recently modified ragas_*.json file."""
    candidates = list(results_dir.glob("ragas_*.json"))
    if not candidates:
        raise ValueError(f"No ragas_*.json files found in {results_dir}.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def run_guard(
    *,
    candidate_path: Path,
    baseline_path: Path,
    min_avg_faithfulness: float,
    q1_index: int,
    max_q1_drop: float,
) -> tuple[bool, list[str]]:
    """Evaluate candidate export against avg and q1 faithfulness guardrails."""
    candidate = _load_payload(candidate_path)
    baseline = _load_payload(baseline_path)

    candidate_avg = _extract_avg_faithfulness(candidate)
    baseline_q1 = _extract_query_faithfulness(baseline, q1_index)
    candidate_q1 = _extract_query_faithfulness(candidate, q1_index)
    q1_drop = baseline_q1 - candidate_q1

    messages = [
        f"Candidate: {candidate_path}",
        f"Baseline:  {baseline_path}",
        f"avg faithfulness={candidate_avg:.3f} (min={min_avg_faithfulness:.3f})",
        f"q{q1_index} faithfulness={candidate_q1:.3f} "
        f"(baseline={baseline_q1:.3f}, drop={q1_drop:.3f}, max_drop={max_q1_drop:.3f})",
    ]

    failed = []
    if candidate_avg < min_avg_faithfulness:
        failed.append("avg_faithfulness_below_min")
    if q1_drop > max_q1_drop:
        failed.append("q1_faithfulness_drop_exceeded")

    if failed:
        messages.append(f"FAIL: {', '.join(failed)}")
        return False, messages
    messages.append("PASS: eval guard checks satisfied.")
    return True, messages


def main() -> int:
    """Run CLI guard check and return process exit code."""
    parser = argparse.ArgumentParser(description="RAGAs faithfulness regression guard")
    parser.add_argument("--candidate", type=Path, default=None)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument(
        "--min-avg-faithfulness", type=float, default=DEFAULT_MIN_AVG_FAITHFULNESS
    )
    parser.add_argument("--q1-index", type=int, default=DEFAULT_Q1_INDEX)
    parser.add_argument("--max-q1-drop", type=float, default=DEFAULT_MAX_Q1_DROP)
    args = parser.parse_args()

    candidate_path = args.candidate or _latest_ragas_export(DEFAULT_RESULTS_DIR)
    passed, messages = run_guard(
        candidate_path=candidate_path,
        baseline_path=args.baseline,
        min_avg_faithfulness=args.min_avg_faithfulness,
        q1_index=args.q1_index,
        max_q1_drop=args.max_q1_drop,
    )
    for line in messages:
        print(line)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
