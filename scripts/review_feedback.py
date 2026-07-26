"""
scripts/review_feedback.py — Performance Review batch driver (agent #24)
=======================================================================
Runs the Performance Review agent (``evaluation/perf_review.py``) over the
answer-level thumbs-down feedback (migration 033) that has not been attributed
yet. This is the arch's *batched, low-volume* trigger — Performance Review never
runs on the query hot path (and ``api/`` may not import ``evaluation/`` anyway).

Each un-reviewed down-vote → one attribution → one *unconfirmed*
``agent_corrections`` row that a superadmin confirms in the dashboard. Priced:
the deterministic classes (errored step, grounding abstain) cost $0; everything
else is one top-tier call. ``--no-llm`` runs the free classes only.

Target-safe (``scripts/_db_target``): dry-run by default, prints the DB banner,
fails fast if unreachable. Writes only with ``--apply``.

    py scripts/review_feedback.py --local --dry-run          # list the queue
    py scripts/review_feedback.py --local --apply            # attribute + write
    py scripts/review_feedback.py --local --apply --no-llm   # deterministic only
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
    parser = argparse.ArgumentParser(description="Performance Review over feedback down-votes.")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--dry-run", action="store_true",
                        help="List the queue only; write nothing (default behaviour).")
    parser.add_argument("--apply", action="store_true",
                        help="Attribute each down-vote and write an unconfirmed correction.")
    parser.add_argument("--no-llm", action="store_true",
                        help="Deterministic attribution only; skip the priced LLM call.")
    parser.add_argument("--days", type=int, default=30,
                        help="Only review down-votes from the last N days (default 30).")
    parser.add_argument("--limit", type=int, default=100,
                        help="Max down-votes to process this run (default 100).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, review each un-attributed down-vote, print a summary."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    apply = args.apply and not args.dry_run

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not apply)
    _db_target.ensure_reachable(target)

    # Import after the target is fixed so db.client binds to the right DSN.
    from db import client as db_client
    from evaluation import perf_review

    since = datetime.now(UTC) - timedelta(days=args.days)
    queue = db_client.list_downvotes_without_review(since=since, limit=args.limit)
    print(f"Un-reviewed down-votes (last {args.days}d): {len(queue)} "
          f"(llm={'off' if args.no_llm else 'on'}, apply={apply})\n")

    if not apply:
        for fb in queue:
            print(f"- run {fb['run_id']} @ {fb['created_at']} "
                  f"comment={(fb.get('comment') or '')[:60]!r}")
        print("\nDry run — nothing written. Re-run with --apply to attribute.")
        return 0

    attributed = 0
    for fb in queue:
        summary = perf_review.review_run(
            fb["run_id"], comment=fb.get("comment"), use_llm=not args.no_llm
        )
        if summary is None:
            print(f"- run {fb['run_id']}: run row missing, skipped")
            continue
        attributed += 1
        who = summary["attributed_agent"] or "UNCLEAR (needs human)"
        print(f"- run {fb['run_id']}: {who} (conf {summary['confidence']:.2f})")

    print(f"\nWrote {attributed} unconfirmed correction(s). Confirm them in "
          f"/admin/agents before they count as training data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
