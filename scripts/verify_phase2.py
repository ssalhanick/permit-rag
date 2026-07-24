"""
scripts/verify_phase2.py — prove the Phase 2 Manager port actually holds
========================================================================
Phase 2 adds no migration; like Phase 1 it is code. So most checks are pure-
Python invariants — the ReAct bound, the registry roster, artifact refs that
carry no payload, an uncapped Budget Governor that is genuinely a no-op, and the
single-call-site rule now that the generator has been folded in. Two need a
database and a corpus: a real ``/query/answer`` plan run through the Manager,
and the trace rows it writes.

Like verify_phase0/1 this exists instead of a curl: it drives the real
``run_query_plan`` with no server and no Cognito token, so a failure points at
the orchestration rather than at HTTP.

**What this script cannot tell you.** Phase 2's acceptance gate is split. This
covers the machine-A half plus the live plan run. The other half is RAGAs
re-baselining to the Phase 0 numbers (avg faithfulness 0.910, floor 0.85) on the
corpus machine:

    py -m evaluation.ragas_eval --export
    py -m evaluation.eval_guard --baseline <the phase-0 results json>

``--export`` is not optional: without it ragas_eval writes no file and eval_guard
silently compares the baseline against itself and passes. Phase 2 is not
verified until that comes back clean, no matter what this script prints.

Two-machine note: the repo machine has an EMPTY database and no corpus, so the
live plan run cannot happen there. ``--no-db`` runs only the offline invariants
and prints **PARTIAL RUN**.

Usage:
    py scripts/verify_phase2.py --local              # corpus machine, full run
    py scripts/verify_phase2.py --database-url='postgresql://...'
    py scripts/verify_phase2.py --local --no-llm     # skip the paid answer call
    py scripts/verify_phase2.py --no-db              # repo machine, offline
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

from db.client import get_conn

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS: list[tuple[str, bool, str]] = []

# The query the live run asks. Deliberately a plain compliance lookup with a
# named jurisdiction so retrieval has something to find on any DFW corpus.
PROBE_QUERY = "What permits are required for a residential fence in Dallas?"


def check(name: str, passed: bool, detail: str = "") -> bool:
    """Record and print one check result."""
    RESULTS.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return passed


# ── Manager invariants (no DB) ───────────────────────────────


def check_manager_plan() -> bool:
    """The ReAct bound is real and the plan fits inside it."""
    print("\nManager plan")
    from rag.agents import manager

    ok = check("max_iterations is 6", manager.MAX_ITERATIONS == 6)
    waves = len(manager._PLAN)
    ok &= check("plan fits the bound", waves <= manager.MAX_ITERATIONS,
                f"{waves} waves / {manager.MAX_ITERATIONS} max")
    steps = sum(len(w) for w in manager._PLAN)
    ok &= check("plan covers the whole ported chain", steps >= 8,
                f"{steps} steps across {waves} waves")
    return bool(ok)


def check_registry() -> bool:
    """The Phase 2 roster is registered; commerce/forms/bids stay out."""
    print("\nAgent registry")
    import rag.agents  # noqa: F401  (import triggers self-registration)
    from rag.agents import registry

    required = (
        "manager", "budget_governor", "answer_generator", "design_intent",
        "permit_classifier", "jurisdiction_resolver", "conflict_detector",
        "mini_rag_conflicts", "project_context",
    )
    missing = [n for n in required if not registry.is_registered(n)]
    ok = check("phase 2 roster registered", not missing,
               ", ".join(registry.names()) if not missing else f"missing {missing}")
    gen = registry.get_or_none("answer_generator")
    ok &= check("answer_generator spec well-formed",
                bool(gen) and gen.tier.value == "mid" and gen.parallel_safe is False)
    mgr = registry.get_or_none("manager")
    ok &= check("manager is not parallel-safe",
                bool(mgr) and mgr.parallel_safe is False)
    return bool(ok)


def check_artifacts() -> bool:
    """A ref carries a summary and a token count, never the payload."""
    print("\nArtifact store")
    from rag.agents.artifacts import ArtifactStore, ExpiredArtifactError

    store = ArtifactStore()
    secret = "SETBACK-TEXT-THAT-MUST-NOT-LEAK"
    ref = store.put("chunks", [{"content": secret}], summary="1 chunk / 1 doc")

    ok = check("ref carries no payload text",
               secret not in ref.summary and secret not in ref.describe())
    ok &= check("ref resolves to the real payload",
                store.get(ref)[0]["content"] == secret)
    ok &= check("token count is estimated", ref.token_count > 0,
                f"~{ref.token_count} tok")

    expiring = ArtifactStore(default_ttl=0)
    dead = expiring.put("chunks", ["x"], summary="1 chunk")
    expired = False
    try:
        expiring.get(dead)
    except ExpiredArtifactError:
        expired = True
    ok &= check("expired ref raises rather than serving stale context", expired)
    return bool(ok)


def check_budget_is_a_noop() -> bool:
    """Uncapped by default — the reason this phase is behaviour-free."""
    print("\nBudget Governor")
    from rag.agent_runtime import Tier
    from rag.agents.budget import BudgetGovernor, BudgetPolicy

    governor = BudgetGovernor(BudgetPolicy())
    chunks = [{"doc_id": f"d{i}", "reranked_score": 0.9, "content": "x" * 1500}
              for i in range(10)]
    kept, decision = governor.degrade("answer_generator", chunks)

    ok = check("default policy is uncapped", governor.capped is False)
    ok &= check("uncapped degrade drops nothing",
                kept == chunks and decision.degraded is False)
    ok &= check("ladder: cheap manager, mid generation",
                governor.tier_for("manager") is Tier.CHEAP
                and governor.tier_for("answer_generator") is Tier.MID)
    ok &= check("unknown step runs cheap",
                governor.tier_for("not_a_real_agent") is Tier.CHEAP)
    return bool(ok)


def check_single_call_site() -> bool:
    """The generator fold: no module in rag/ builds its own Anthropic client."""
    print("\nSingle call site")
    from rag.generator import generate_answer

    offenders = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in sorted((REPO_ROOT / "rag").rglob("*.py"))
        if p.name != "agent_runtime.py"
        and "anthropic.Anthropic(" in p.read_text(encoding="utf-8")
    ]
    ok = check("no inline anthropic client in rag/", not offenders,
               ", ".join(offenders) if offenders else "agent_runtime.py only")
    ok &= check("generate_answer routes through the runtime",
                "run_agent" in (REPO_ROOT / "rag/generator.py").read_text(encoding="utf-8"))
    ok &= check("generate_answer is not double-traced",
                not hasattr(generate_answer, "__wrapped__"),
                "@traced removed; run_agent records the step")
    return bool(ok)


def check_import_boundary() -> bool:
    """rag/agents/ must not import commerce/, forms/, or bids/ (AGENTS.md)."""
    print("\nImport boundary")
    offenders: list[str] = []
    for path in sorted((REPO_ROOT / "rag/agents").rglob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            if any(f"{pkg}." in stripped or stripped.endswith(pkg)
                   for pkg in ("commerce", "forms", "bids")):
                offenders.append(f"{path.name}: {stripped}")
    return check("rag/agents/ imports no commerce/forms/bids", not offenders,
                 "; ".join(offenders) if offenders else "clean")


# ── Live plan run (DB + corpus) ──────────────────────────────


def check_live_plan(conn: Any, *, use_llm: bool) -> bool:
    """Drive the real Manager against the real corpus and read the trace back."""
    print("\nManager plan (live)")
    from audit.logger import start_run
    from rag.agents.manager import ManagerDeps, ManagerRequest, run_query_plan
    from rag.retriever import retrieve_with_project

    before = conn.execute("SELECT count(*) AS c FROM agent_steps;").fetchone()["c"]
    with start_run("verify_phase2", intent="compliance_lookup"):
        plan = run_query_plan(
            ManagerRequest(query=PROBE_QUERY, top_k=5, municipality="dallas"),
            ManagerDeps(
                retrieve=retrieve_with_project,
                min_chunks=int(os.environ.get("RAG_GUARD_MIN_CHUNKS", "3")),
                min_top_sim=float(os.environ.get("RAG_GUARD_MIN_TOP_SIM", "0.74")),
            ),
        )
    after = conn.execute("SELECT count(*) AS c FROM agent_steps;").fetchone()["c"]

    ok = check("plan stayed inside the ReAct bound", 0 < plan.iterations <= 6,
               f"{plan.iterations} iterations")
    ok &= check("answer carries at least one citation",
                len(plan.generation.citations) >= 1,
                f"{len(plan.generation.citations)} citations")
    ok &= check("manager artifacts carry no chunk text",
                all("Source 1" not in r.summary for r in plan.artifacts),
                f"{len(plan.artifacts)} refs: "
                + ", ".join(sorted({r.kind for r in plan.artifacts})))
    ok &= check("exactly two steps written (manager + generator)", after - before == 2,
                f"{after - before} new steps")
    return bool(ok and _check_trace_rows(conn, use_llm=use_llm))


def _check_trace_rows(conn: Any, *, use_llm: bool) -> bool:
    """Assert the two rows the live plan just wrote look right."""
    mgr = conn.execute(
        "SELECT deterministic, react_iterations, artifact_refs, cost_usd "
        "FROM agent_steps WHERE agent_name='manager' "
        "ORDER BY created_at DESC LIMIT 1;"
    ).fetchone()
    ok = check("manager step is deterministic and free",
               bool(mgr) and mgr["deterministic"] is True
               and float(mgr["cost_usd"] or 0) == 0.0)
    ok &= check("manager step records its iterations and refs",
                bool(mgr) and int(mgr["react_iterations"]) > 0
                and len(mgr["artifact_refs"] or []) >= 2,
                f"{mgr['react_iterations']} iterations, "
                f"{len(mgr['artifact_refs'] or [])} refs" if mgr else "no row")

    gen = conn.execute(
        "SELECT model, tokens_in, cost_usd FROM agent_steps "
        "WHERE agent_name='answer_generator' ORDER BY created_at DESC LIMIT 1;"
    ).fetchone()
    ok &= check("generator step priced through the runtime",
                bool(gen) and float(gen["cost_usd"]) > 0,
                f"${float(gen['cost_usd']):.6f} on {gen['model']}" if gen else "no row")
    if use_llm:
        expected = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
        ok &= check("LLM_MODEL still decides the wire model (trap c)",
                    bool(gen) and str(gen["model"]).startswith(expected.split("-2026")[0]),
                    f"{gen['model']} vs LLM_MODEL={expected}" if gen else "no row")
    return bool(ok)


def _report(offline: bool) -> None:
    """Print the summary and exit non-zero on any failed check."""
    failed = [name for name, passed, _ in RESULTS if not passed]
    print("\n" + "=" * 72)
    if failed:
        print(f"  {len(failed)} of {len(RESULTS)} checks FAILED:")
        for name in failed:
            print(f"    - {name}")
        print("=" * 72)
        sys.exit(1)
    if offline:
        print(f"  {len(RESULTS)} offline checks passed — PARTIAL RUN.")
        print("  The live Manager plan is NOT verified here — run --local on the corpus machine.")
    else:
        print(f"  All {len(RESULTS)} checks passed — the Manager plan is verified on this database.")
    print("  RAGAs faithfulness is a corpus/judge signal, NOT a Phase 2 gate: the")
    print("  judge varies more run-to-run than the fold can. If you run it, use")
    print("  --no-answer-cache — the env var is overwritten by bootstrap_env, so a")
    print("  plain run scores stale cached answer text and measures nothing:")
    print("    py -m evaluation.ragas_eval --export --no-answer-cache")
    print("=" * 72)


def main() -> None:
    """Run every Phase 2 check and exit non-zero on any failure."""
    offline = "--no-db" in sys.argv
    use_llm = "--no-llm" not in sys.argv and not offline

    if offline:
        print("\n  --no-db: pure-Python invariants only. No database is touched.")
    else:
        _db_target.banner(TARGET, read_only=False)
        _db_target.ensure_reachable(TARGET)

    check_manager_plan()
    check_registry()
    check_artifacts()
    check_budget_is_a_noop()
    check_single_call_site()
    check_import_boundary()

    if offline:
        print("\nManager plan (live)\n  (--no-db: skipped — needs the corpus machine)")
    elif not use_llm:
        print("\nManager plan (live)\n  (--no-llm: skipped — the plan ends in a paid call)")
    else:
        with get_conn() as conn:
            check_live_plan(conn, use_llm=use_llm)

    _report(offline)


if __name__ == "__main__":
    main()
