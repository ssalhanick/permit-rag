"""
scripts/seed_media_refs.py — load curated how-to video links into media_refs.

The Media Curator (agent #17) surfaces only vetted links. This seeds the
``media_refs`` table from a git-tracked JSON of hand-verified entries, so the
corpus of links is reviewable in version control rather than typed ad hoc.

Target-safe via scripts/_db_target (never a bare bootstrap_env — this repo's
recurring footgun). Dry-run by default; ``--apply`` writes. Idempotent: rows are
deduped on (task_key, url), so re-running inserts only what is new.

    py scripts/seed_media_refs.py --local                 # dry-run, show plan
    py scripts/seed_media_refs.py --local --apply         # write new rows
    py scripts/seed_media_refs.py --local --apply --verified   # stamp last_verified_at=now

**Every URL in the seed JSON must be human-verified before it lands.** Pass
``--verified`` only when you have actually opened each link; it stamps
``last_verified_at`` so the (future) liveness watcher knows the baseline.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

_DEFAULT_SEED = Path(__file__).resolve().parent / "media_refs_seed.json"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed media_refs from curated JSON.")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--apply", action="store_true", help="Write rows (default: dry-run).")
    parser.add_argument(
        "--verified", action="store_true",
        help="Stamp last_verified_at=now (assert you checked every link).",
    )
    parser.add_argument("--seed", default=str(_DEFAULT_SEED), help="Path to the seed JSON.")
    parser.add_argument(
        "--prune-placeholders", action="store_true",
        help="Delete un-vetted placeholder rows (url/title still says REPLACE), then exit.",
    )
    return parser.parse_args(argv)


def _load_seed(path: Path) -> list[dict]:
    """Read and lightly validate the curated seed entries.

    Refuses the shipped placeholders: a URL/title still carrying ``REPLACE`` means
    the entry was never vetted, and inserting a dead link is the exact failure the
    Media Curator exists to prevent. Replace every placeholder with a real,
    human-checked link before seeding.
    """
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path} must contain a JSON array of entries")
    for r in rows:
        for key in ("task_key", "title", "url"):
            if not r.get(key):
                raise ValueError(f"seed entry missing '{key}': {r}")
        if not str(r["url"]).startswith("https://"):
            raise ValueError(f"seed url must be https: {r['url']}")
        # The shipped placeholder URLs carry this exact sentinel. Match only it —
        # not the word "replace", which is legitimate in a title like
        # "How to replace a faucet".
        if "REPLACE_WITH_VERIFIED_ID" in str(r["url"]).upper():
            raise ValueError(
                f"placeholder entry not yet vetted: {r['task_key']}. "
                "Edit scripts/media_refs_seed.json with a real, human-verified link first."
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, then dry-run or apply the curated seed."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # Prune runs before loading the seed (the seed now refuses placeholders, so a
    # cleanup path must not require a valid seed file to exist).
    if args.prune_placeholders:
        target = _db_target.resolve(sys.argv[1:], bootstrap_env)
        _db_target.banner(target, read_only=False)
        _db_target.ensure_reachable(target)
        from db.client import delete_placeholder_media_refs

        removed = delete_placeholder_media_refs()
        print(f"\nPruned {removed} placeholder media_refs row(s).")
        return 0

    seed_path = Path(args.seed)
    rows = _load_seed(seed_path)

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not args.apply)
    _db_target.ensure_reachable(target)

    print(f"\nSeed file: {seed_path}  ({len(rows)} curated entries)")
    if not args.apply:
        for r in rows:
            juris = r.get("jurisdiction") or "national"
            print(f"  [dry-run] {r['task_key']:28} {juris:10} {r['url']}")
        print("\nDry run — nothing written. Re-run with --apply to insert.")
        return 0

    from db.client import insert_media_ref

    verified_at = datetime.now(UTC) if args.verified else None
    inserted = 0
    for r in rows:
        row = insert_media_ref(
            task_key=r["task_key"],
            title=r["title"],
            url=r["url"],
            provider=r.get("provider", "youtube"),
            jurisdiction=r.get("jurisdiction"),
            relevance_note=r.get("relevance_note"),
            last_verified_at=verified_at,
        )
        status = "inserted" if row else "exists"
        if row:
            inserted += 1
        print(f"  [{status}] {r['task_key']:28} {r['url']}")

    print(f"\nDone. {inserted} new row(s); {len(rows) - inserted} already present.")
    if not args.verified:
        print("Note: last_verified_at left NULL. Re-run with --verified once links are checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
