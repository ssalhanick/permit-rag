"""
scripts/verify_phase0.py — prove the Phase 0 trace store actually works
=======================================================================
Runs every Phase 0 acceptance check against one database and prints a
pass/fail table.

Why this exists rather than a curl against /api/query/answer: that route
requires a real Cognito bearer token, and `curl` in PowerShell is an alias for
Invoke-WebRequest, which rejects bash-style flags. This exercises the same
instrumentation (start_run -> generate_answer, exactly as the route does) with
no server, no token, and no shell-syntax differences between platforms.

Makes ONE real model call (a few tenths of a cent on haiku) because token
accounting and cost math are the things being verified. Writes rows to
agent_runs / agent_steps -- that is the point. Nothing is deleted.

Usage:
    py scripts/verify_phase0.py --local
    py scripts/verify_phase0.py --database-url='postgresql://...'
    py scripts/verify_phase0.py --local --no-llm    # skip the model call
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

from db.client import get_conn

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> bool:
    """Record and print one check result."""
    RESULTS.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return passed


# ── Schema ───────────────────────────────────────────────────


def check_schema(conn: Any) -> bool:
    """Migrations 026 and 027, plus the seeded autonomy ceilings."""
    print("\nSchema")
    tables = conn.execute(
        "SELECT count(*) AS c FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name IN "
        "('agent_runs','agent_steps','agent_corrections',"
        "'agent_action_items','agent_autonomy');"
    ).fetchone()["c"]
    ok = check("026 tables present", tables == 5, f"{tables}/5")

    row = conn.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name='agent_action_items' AND column_name='entity_type';"
    ).fetchone()
    ok &= check(
        "027 dedupe fix applied",
        bool(row) and row["is_nullable"] == "NO",
        "entity_type NOT NULL" if row and row["is_nullable"] == "NO"
        else "entity_type still nullable — apply 027",
    )

    seeded = conn.execute("SELECT count(*) AS c FROM agent_autonomy;").fetchone()["c"]
    ok &= check("autonomy ceilings seeded", seeded >= 15, f"{seeded} rows")
    return bool(ok)


def check_autonomy_clamp(conn: Any) -> bool:
    """A level above max_level must be refused by the database itself."""
    print("\nAutonomy enforcement")
    row = conn.execute(
        "SELECT current_level, max_level FROM agent_autonomy "
        "WHERE agent_name='web_form_navigator' AND scope='submit';"
    ).fetchone()
    if not row:
        return check("submit ceiling seeded", False, "row missing")
    ok = check(
        "web_form_navigator/submit capped at L1",
        row["max_level"] == "L1",
        f"max_level={row['max_level']}",
    )

    # db.client.set_agent_autonomy clamps in SQL: an over-ceiling request
    # matches no row and returns None.
    from db.client import set_agent_autonomy

    refused = set_agent_autonomy("web_form_navigator", "submit", current_level="L3")
    ok &= check("L3 request refused by SQL clamp", refused is None)
    return bool(ok)


# ── Corpus ───────────────────────────────────────────────────


def check_corpus(conn: Any) -> bool:
    """Retrieval cannot work without embedded chunks."""
    print("\nCorpus")
    row = conn.execute(
        "SELECT (SELECT count(*) FROM documents) AS docs, "
        "       (SELECT count(*) FROM chunks) AS chunks, "
        "       (SELECT count(*) FROM chunks WHERE embedding IS NOT NULL) AS embedded;"
    ).fetchone()
    ok = check("documents ingested", row["docs"] > 0, f"{row['docs']} docs")
    ok &= check("chunks embedded", row["embedded"] > 0,
                f"{row['embedded']}/{row['chunks']} chunks")

    # 022 may not be applied; querying its column blind would abort the whole
    # run on UndefinedColumn instead of reporting one failed check.
    has_022 = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name='documents' AND column_name='source_url_normalized') "
        "AS present;"
    ).fetchone()["present"]
    if not has_022:
        ok &= check(
            "022 identity keys backfilled",
            False,
            "migration 022 not applied — "
            "py scripts/apply_migration.py db/migrations/022_source_identity.sql",
        )
        return bool(ok)

    missing = conn.execute(
        "SELECT count(*) AS c FROM documents WHERE source_url_normalized IS NULL;"
    ).fetchone()["c"]
    ok &= check(
        "022 identity keys backfilled",
        missing == 0,
        "complete" if missing == 0
        else f"{missing} unbackfilled — run scripts/backfill_source_identity.py",
    )
    return bool(ok)


# ── The trace store itself ───────────────────────────────────


def check_tracing(conn: Any, *, use_llm: bool) -> bool:
    """
    Exercise the real instrumentation and confirm rows land.

    Mirrors api/routes/query.py: @traced_run opens the run, @traced on
    generate_answer records the step. Retrieval is filtered to passing_chunks
    exactly as the route does.
    """
    print("\nTrace store")
    from audit.logger import start_run
    from rag.generator import drop_filtered_chunks, generate_answer
    from rag.retriever import retrieve

    query = "What are the setback requirements for a residential fence in Dallas?"

    result = retrieve(query, top_k=5, municipality="dallas")
    ok = check("retrieval returns chunks", result.num_results > 0,
               f"{result.num_results} chunks, top_sim={result.top_similarity:.3f}")
    if not ok:
        return False

    rejected = len(result.chunks) - len(result.passing_chunks)
    check("reranker-rejected chunks identified", True,
          f"{rejected} filtered_out of {len(result.chunks)}")
    ok &= check(
        "filtered_out chunks dropped before prompting",
        len(drop_filtered_chunks(result.chunks)) == len(result.passing_chunks),
    )

    if not use_llm:
        print("  (--no-llm: skipping generation, so no step row is written)")
        return bool(ok)

    before = conn.execute("SELECT count(*) AS c FROM agent_steps;").fetchone()["c"]
    with start_run("verify_phase0", intent="compliance_lookup"):
        gen = generate_answer(query, result.passing_chunks)

    after = conn.execute("SELECT count(*) AS c FROM agent_steps;").fetchone()["c"]
    ok &= check("step row written", after > before, f"{after - before} new step(s)")

    step = conn.execute(
        "SELECT agent_name, model, tokens_in, tokens_out, cost_usd, "
        "       tokens_cache_read, latency_ms "
        "FROM agent_steps ORDER BY created_at DESC LIMIT 1;"
    ).fetchone()
    if not step:
        return False
    ok &= check("step names the agent", step["agent_name"] == "answer_generator",
                str(step["agent_name"]))
    ok &= check("tokens recorded", step["tokens_in"] > 0 and step["tokens_out"] > 0,
                f"{step['tokens_in']} in / {step['tokens_out']} out")
    ok &= check("cost computed", float(step["cost_usd"]) > 0,
                f"${float(step['cost_usd']):.6f} on {step['model']}")

    run = conn.execute(
        "SELECT outcome, cost_usd, latency_ms FROM agent_runs "
        "WHERE entrypoint='verify_phase0' ORDER BY created_at DESC LIMIT 1;"
    ).fetchone()
    ok &= check("run closed and totals rolled up",
                bool(run) and run["outcome"] == "success"
                and float(run["cost_usd"]) > 0,
                f"outcome={run['outcome']}, ${float(run['cost_usd']):.6f}, "
                f"{run['latency_ms']}ms" if run else "no run row")

    # Informational: cache reads are expected to be 0 until the Phase 4
    # Prompt Router gives the prefix something stable to cache.
    print(f"  [info] cache_read_input_tokens={step['tokens_cache_read']} "
          "(0 is expected before Phase 4)")
    print(f"  [info] answer {len(gen.answer)} chars, {len(gen.citations)} citations")
    return bool(ok)


def main() -> None:
    """Run every Phase 0 check and exit non-zero on any failure."""
    _db_target.banner(TARGET, read_only=False)
    _db_target.ensure_reachable(TARGET)
    use_llm = "--no-llm" not in sys.argv

    with get_conn() as conn:
        check_schema(conn)
        check_autonomy_clamp(conn)
        corpus_ok = check_corpus(conn)
        if corpus_ok:
            check_tracing(conn, use_llm=use_llm)
        else:
            print("\nTrace store\n  (skipped — no corpus to retrieve from)")

    failed = [name for name, passed, _ in RESULTS if not passed]
    print("\n" + "=" * 72)
    if failed:
        print(f"  {len(failed)} of {len(RESULTS)} checks FAILED:")
        for name in failed:
            print(f"    - {name}")
        print("=" * 72)
        sys.exit(1)
    print(f"  All {len(RESULTS)} checks passed — Phase 0 is complete on this database.")
    print("=" * 72)


if __name__ == "__main__":
    main()
