"""
scripts/seed_labor_rate_benchmarks.py — load seeded DFW hourly-rate ranges
into labor_rate_benchmarks.

bids/pricing.py's price-reasonableness check compares a bid line item's
labor_amount / labor_hours against these ranges. No free authoritative rate
source exists (RSMeans is paid) -- this seeds public, non-authoritative DFW
estimate ranges; every price-reasonableness output derived from this table
must be labeled an estimate with its source (docs/agent_architecture.md).

Target-safe via scripts/_db_target (never a bare bootstrap_env — this repo's
recurring footgun). Dry-run by default; --apply writes. Idempotent: rows are
deduped on (trade, region).

    py scripts/seed_labor_rate_benchmarks.py --local
    py scripts/seed_labor_rate_benchmarks.py --local --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

_DEFAULT_SEED = Path(__file__).resolve().parent / "labor_rate_benchmarks_seed.json"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed labor_rate_benchmarks from curated JSON.")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--apply", action="store_true", help="Write rows (default: dry-run).")
    parser.add_argument("--seed", default=str(_DEFAULT_SEED), help="Path to the seed JSON.")
    return parser.parse_args(argv)


def _load_seed(path: Path) -> list[dict]:
    """Read and lightly validate the curated seed entries."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array of entries")
    for r in rows:
        for key in ("trade", "low_hourly_rate", "high_hourly_rate", "source"):
            if r.get(key) in (None, ""):
                raise ValueError(f"seed entry missing '{key}': {r}")
        if r["low_hourly_rate"] > r["high_hourly_rate"]:
            raise ValueError(f"low_hourly_rate exceeds high_hourly_rate: {r}")
    return rows


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, then dry-run or apply the curated seed."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    rows = _load_seed(Path(args.seed))

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not args.apply)
    _db_target.ensure_reachable(target)

    print(f"\nSeed file: {args.seed}  ({len(rows)} curated entries)")
    if not args.apply:
        for r in rows:
            region = r.get("region", "DFW")
            print(f"  [dry-run] {r['trade']:24} ${r['low_hourly_rate']}-${r['high_hourly_rate']}/hr  ({region})")
        print("\nDry run — nothing written. Re-run with --apply to insert.")
        return 0

    from db.client import insert_labor_rate_benchmark

    inserted = 0
    for r in rows:
        row = insert_labor_rate_benchmark(
            trade=r["trade"],
            region=r.get("region", "DFW"),
            low_hourly_rate=r["low_hourly_rate"],
            high_hourly_rate=r["high_hourly_rate"],
            source=r["source"],
            effective_date=r.get("effective_date"),
        )
        status = "inserted" if row else "exists"
        if row:
            inserted += 1
        print(f"  [{status}] {r['trade']}")

    print(f"\nDone. {inserted} new row(s); {len(rows) - inserted} already present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
