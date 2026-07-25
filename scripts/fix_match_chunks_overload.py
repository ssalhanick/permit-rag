"""
scripts/fix_match_chunks_overload.py — drop the orphaned 4-arg match_chunks.

A one-off cleanup for local DBs that applied the PRE-RELEASE (breaking) version of
migration 031, which created a 4-arg ``match_chunks(vector,int,text,text)``. The
shipped (non-breaking) 031 uses ``CREATE OR REPLACE`` on the 3-arg signature and
does not remove that stray 4-arg, so both coexist and a 3-arg call errors with
"function match_chunks(...) is not unique". Prod never had the 4-arg (it only ever
applied the non-breaking 031), so this is a no-op there.

Target-safe via scripts/_db_target (this repo's rule: never a bare bootstrap_env).
Prints the overloads before and after so you can confirm exactly one remains.

    py scripts/fix_match_chunks_overload.py --local
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

_LIST_SQL = (
    "SELECT oid::regprocedure::text AS sig FROM pg_proc "
    "WHERE proname = 'match_chunks' ORDER BY 1;"
)
_DROP_SQL = "DROP FUNCTION IF EXISTS match_chunks(vector, integer, text, text);"


def main() -> int:
    """Drop the 4-arg match_chunks overload on the resolved target."""
    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=False)
    _db_target.ensure_reachable(target)

    from db.client import get_conn

    with get_conn() as conn:
        before = [r["sig"] for r in conn.execute(_LIST_SQL).fetchall()]
        print(f"\nmatch_chunks overloads before: {before}")
        conn.execute(_DROP_SQL)
        conn.commit()
        after = [r["sig"] for r in conn.execute(_LIST_SQL).fetchall()]

    print(f"match_chunks overloads after:  {after}")
    if len(after) == 1:
        print("✓ Exactly one match_chunks remains — the ambiguity is resolved.")
        return 0
    print("⚠ Expected exactly one overload; inspect the list above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
