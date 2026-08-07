"""
scripts/run_agent_eval.py — Evaluator batch driver (agent #23)
=============================================================
Scores every agent against its metric contract (``evaluation/agent_eval.py``)
over a recent window of trace data. Deterministic — no model spend. Dry-run by
default (report only); ``--apply`` files a ``metric_contract_breach`` action item
for each breached agent and auto-demotes it one autonomy level (the arch's
"a breach auto-demotes one level and writes an action item").

Machine B — needs the trace store filled by real traffic.

    py scripts/run_agent_eval.py --local --days 7            # report only
    py scripts/run_agent_eval.py --local --days 7 --apply    # file items + demote
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI flags. --apply is the only thing that writes anything."""
    parser = argparse.ArgumentParser(description="Evaluator: per-agent metric contracts.")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only; file nothing, demote nothing (default).")
    parser.add_argument("--apply", action="store_true",
                        help="File a breach action item + auto-demote each breached agent.")
    parser.add_argument("--days", type=int, default=7,
                        help="Evaluate the trace window of the last N days (default 7).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, evaluate the contracts, print a per-agent report."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    apply = args.apply and not args.dry_run

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not apply)
    _db_target.ensure_reachable(target)

    from evaluation import agent_eval

    since = datetime.now(UTC) - timedelta(days=args.days)
    reports = agent_eval.evaluate(since=since, apply=apply)
    if not reports:
        print(f"No agent traces in the last {args.days}d — nothing to evaluate.")
        return 0

    breached = 0
    for r in reports:
        status = "PASS" if r.passed else "BREACH"
        print(f"[{status}] {r.agent}  "
              f"det={r.metrics.get('deterministic_rate', 0):.2f} "
              f"err={r.metrics.get('error_rate', 0):.2f} "
              f"corr={r.metrics.get('correction_rate', 0):.2f}"
              + (f" faith={r.metrics['faithfulness']:.3f}" if 'faithfulness' in r.metrics else ""))
        for b in r.breaches:
            print(f"        - {b}")
        for a in r.advisories:
            print(f"        ~ [advisory, not gating] {a}")
        if not r.passed:
            breached += 1
            if r.demoted_to:
                print(f"        → demoted to {r.demoted_to}")

    if not apply and breached:
        print(f"\n{breached} agent(s) in breach. Re-run with --apply to file items + demote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
