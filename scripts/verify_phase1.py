"""
scripts/verify_phase1.py — prove the Phase 1 runtime + registry actually work
=============================================================================
Phase 1 adds no migration; it is code. So most checks are pure-Python
invariants (model ladder, cache-prefix thresholds, registry self-registration)
that need no database, plus two that do: autonomy enforcement reads
`agent_autonomy`, and the live runtime call writes a trace step through the
single Anthropic call site.

Like verify_phase0.py this exists instead of a curl: it exercises the real
`run_agent` path with no server and no Cognito token. The live section makes
TWO real haiku calls behind a >4096-token cached system prefix so it can assert
`cache_read_input_tokens > 0` on the second — the caching guarantee Phase 0
could not yet verify. Skip it with --no-llm.

Usage:
    py scripts/verify_phase1.py --local
    py scripts/verify_phase1.py --database-url='postgresql://...'
    py scripts/verify_phase1.py --local --no-llm
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


# ── Runtime invariants (no DB) ───────────────────────────────


def check_runtime_invariants() -> bool:
    """The model ladder and the cache-prefix thresholds are the plan's."""
    print("\nRuntime invariants")
    from rag.agent_runtime import Tier, min_cache_prefix, model_for_tier

    ladder_ok = (
        model_for_tier(Tier.CHEAP) == "claude-haiku-4-5"
        and model_for_tier(Tier.MID) == "claude-sonnet-5"
        and model_for_tier(Tier.TOP) == "claude-opus-4-8"
    )
    ok = check("model ladder cheap/mid/top", ladder_ok)
    ok &= check(
        "cache minimum prefix 4096/2048",
        min_cache_prefix("claude-haiku-4-5") == 4096
        and min_cache_prefix("claude-opus-4-8") == 4096
        and min_cache_prefix("claude-sonnet-5") == 2048,
    )
    return bool(ok)


def check_registry() -> bool:
    """rag self-registers its own agents; commerce/forms/bids stay out."""
    print("\nAgent registry")
    import rag.agents  # noqa: F401  (import triggers self-registration)
    from rag.agents import registry

    ok = check(
        "rag agents self-registered",
        registry.is_registered("answer_generator")
        and registry.is_registered("design_intent"),
        ", ".join(registry.names()),
    )
    gen = registry.get_or_none("answer_generator")
    ok &= check("answer_generator spec well-formed",
                bool(gen) and gen.tier.value == "mid" and gen.parallel_safe is False)
    return bool(ok)


# ── Autonomy enforcement (DB) ────────────────────────────────


def check_autonomy() -> bool:
    """Fail-closed default and the SQL-seeded submit ceiling, via the runtime."""
    print("\nAutonomy enforcement (runtime)")
    from rag.agent_runtime import (
        AutonomyError,
        enforce_autonomy,
        resolve_autonomy_level,
    )

    ok = check(
        "unregistered agent defaults to L0",
        resolve_autonomy_level("definitely_not_a_real_agent") == "L0",
    )
    refused = False
    try:
        enforce_autonomy("web_form_navigator", "L3", scope="submit")
    except AutonomyError:
        refused = True
    ok &= check("L3 action on web_form_navigator/submit refused by runtime", refused)
    return bool(ok)


# ── Live runtime call (traced, cached, structured) ───────────


def check_live_runtime(conn: Any) -> bool:
    """One structured + one cached call through the single Anthropic call site."""
    print("\nSingle call site (live)")
    from pydantic import BaseModel

    from audit.logger import start_run
    from rag.agent_runtime import Tier, run_agent

    class Ack(BaseModel):
        acknowledged: bool

    # A >4096-token stable prefix so the cache breakpoint is real, not silent.
    big_prefix = ("You are a permit-compliance assistant for the DFW market. "
                  "Answer only from provided context. " * 400)

    before = conn.execute("SELECT count(*) AS c FROM agent_steps;").fetchone()["c"]
    with start_run("verify_phase1", intent="compliance_lookup"):
        run_agent("verify_phase1_probe", system=big_prefix,
                  messages=[{"role": "user", "content": "Reply with acknowledged=true."}],
                  tier=Tier.CHEAP, output_format=Ack, cache_ttl_1h=True)
        second = run_agent("verify_phase1_probe", system=big_prefix,
                           messages=[{"role": "user", "content": "Reply acknowledged=true again."}],
                           tier=Tier.CHEAP, output_format=Ack, cache_ttl_1h=True)

    after = conn.execute("SELECT count(*) AS c FROM agent_steps;").fetchone()["c"]
    ok = check("steps written through the runtime", after - before == 2,
               f"{after - before} new steps")

    step = conn.execute(
        "SELECT agent_name, model, tokens_in, cost_usd, tokens_cache_read "
        "FROM agent_steps WHERE agent_name='verify_phase1_probe' "
        "ORDER BY created_at DESC LIMIT 1;"
    ).fetchone()
    ok &= check("step names the probe and costs > 0",
                bool(step) and step["agent_name"] == "verify_phase1_probe"
                and float(step["cost_usd"]) > 0,
                f"${float(step['cost_usd']):.6f} on {step['model']}" if step else "no row")
    ok &= check(
        "prompt caching active (cache_read > 0 on 2nd call)",
        int(step["tokens_cache_read"]) > 0 if step else False,
        f"cache_read={step['tokens_cache_read']}" if step else "",
    )
    ok &= check("structured output parsed", second.parsed_output is not None,
                f"acknowledged={getattr(second.parsed_output, 'acknowledged', None)}")
    return bool(ok)


def main() -> None:
    """Run every Phase 1 check and exit non-zero on any failure."""
    _db_target.banner(TARGET, read_only=False)
    _db_target.ensure_reachable(TARGET)
    use_llm = "--no-llm" not in sys.argv

    check_runtime_invariants()
    check_registry()
    with get_conn() as conn:
        check_autonomy()
        if use_llm:
            check_live_runtime(conn)
        else:
            print("\nSingle call site (live)\n  (--no-llm: skipped)")

    failed = [name for name, passed, _ in RESULTS if not passed]
    print("\n" + "=" * 72)
    if failed:
        print(f"  {len(failed)} of {len(RESULTS)} checks FAILED:")
        for name in failed:
            print(f"    - {name}")
        print("=" * 72)
        sys.exit(1)
    print(f"  All {len(RESULTS)} checks passed — Phase 1 is complete on this database.")
    print("=" * 72)


if __name__ == "__main__":
    main()
