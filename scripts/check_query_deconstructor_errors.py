"""
scripts/check_query_deconstructor_errors.py — root-cause query_deconstructor's
error rate
============================================================================
`scripts/run_agent_eval.py` reported `query_deconstructor` at 100% step error
rate on Machine B (det=0.00 err=1.00). `deconstruct()` (rag/agents/deconstructor.py)
never lets a `run_agent()` failure reach its caller -- it swallows the
exception and degrades to the single-question form -- but `run_agent()`
(rag/agent_runtime.py) still records the failed attempt as a `status="error"`
`agent_steps` row before that exception is caught. This prints the actual
recorded errors so we can tell a credential/environment issue apart from a
real bug in the `Deconstruction` structured-output call.

READ-ONLY. Issues no writes.

Usage:
    py scripts/check_query_deconstructor_errors.py --local
    py scripts/check_query_deconstructor_errors.py --database-url='postgresql://...'
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

from db.client import get_conn


def main() -> None:
    """Print every recorded query_deconstructor error step, newest first."""
    _db_target.banner(TARGET)
    _db_target.ensure_reachable(TARGET, get_conn)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, error, latency_ms, created_at "
            "FROM agent_steps "
            "WHERE agent_name = 'query_deconstructor' "
            "ORDER BY created_at DESC "
            "LIMIT 20;"
        ).fetchall()

    if not rows:
        print("No agent_steps rows found for query_deconstructor in this database.")
        return

    ok = sum(1 for r in rows if r["status"] == "ok")
    err = len(rows) - ok
    print(f"Most recent {len(rows)} query_deconstructor step(s): {ok} ok, {err} error\n")
    for r in rows:
        print(f"[{r['created_at']}] status={r['status']} latency_ms={r['latency_ms']}")
        if r["error"]:
            print(f"    error: {r['error']}")


if __name__ == "__main__":
    main()
