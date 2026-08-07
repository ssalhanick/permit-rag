"""
scripts/verify_query_deconstructor_fix.py — confirm the effort-parameter fix
live
=============================================================================
`check_query_deconstructor_errors.py` only reads *historical* agent_steps
rows -- it can't show the fix working, since old error rows don't change
retroactively. This makes one real compound-query call through
`deconstruct()` (the same call `rag/agents/manager.py::_deconstruct` makes)
and reports whether it actually split into sub-questions this time, plus
prints the freshly-recorded agent_steps row for it.

Costs one real cheap-tier (haiku) API call. Issues no DB writes beyond the
one `agent_steps` row `run_agent` always records for any call, tracing.

Usage:
    py scripts/verify_query_deconstructor_fix.py --local
    py scripts/verify_query_deconstructor_fix.py --database-url='postgresql://...'
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

from audit.logger import start_run
from db.client import get_conn
from rag.agents.deconstructor import deconstruct

_COMPOUND_QUERY = (
    "What are the setback and height limits for a garage in Plano, and "
    "do I need an electrical permit?"
)


def main() -> None:
    """Run one real deconstruct() call and report the outcome plus its trace."""
    _db_target.banner(TARGET)
    _db_target.ensure_reachable(TARGET, get_conn)

    with start_run("verify_query_deconstructor_fix"):
        result = deconstruct(_COMPOUND_QUERY)

    print(f"is_compound = {result.is_compound}")
    print(f"sub_questions ({len(result.sub_questions)}):")
    for sq in result.sub_questions:
        print(f"  - {sq.text!r} (municipality={sq.municipality}, permit_type={sq.permit_type})")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT status, error, latency_ms, created_at FROM agent_steps "
            "WHERE agent_name = 'query_deconstructor' "
            "ORDER BY created_at DESC LIMIT 1;"
        ).fetchone()

    print("\nMost recent agent_steps row for query_deconstructor:")
    if row is None:
        print("  none found")
    else:
        print(f"  status={row['status']} latency_ms={row['latency_ms']} created_at={row['created_at']}")
        if row["error"]:
            print(f"  error: {row['error']}")

    if result.is_compound and row is not None and row["status"] == "ok":
        print("\n✅ Fix confirmed: real call succeeded and split into sub-questions.")
    else:
        print("\n⚠ Not yet confirmed — see status/error above.")


if __name__ == "__main__":
    main()
