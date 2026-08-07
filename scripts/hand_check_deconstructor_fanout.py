"""
scripts/hand_check_deconstructor_fanout.py — does fan-out retrieval actually
help on genuinely compound queries?
=============================================================================
STATE.md's Phase 5 tail has always called for hand-checking a few compound
queries before trusting Query Deconstructor #5's fan-out retrieval
(rag/agents/manager.py::_fanout_retrieval) -- never done, because the
effort-parameter bug (see check_query_deconstructor_errors.py /
verify_query_deconstructor_fix.py) meant deconstruct() always failed and
fanout never fired. Now that it's fixed, this is meaningful for the first
time.

For each compound query below, prints:
  - the sub-questions the Deconstructor split it into
  - the chunks retrieved via fan-out -- calls rag.agents.manager._fanout_retrieval
    directly (via a constructed _PlanState), not a hand-copied reimplementation.
    2026-08-07: this script's first version *did* hand-copy the merge logic, which
    meant it kept reproducing a bug (missing municipality canonicalization) even
    after that bug was fixed in manager.py itself, since the script's own copy
    never got the fix. Calling the real function is what makes a re-run actually
    prove anything about the production code path.
  - the chunks retrieved via the single-question path (rag.agents.manager._single_retrieval,
    same real-function approach) -- what every query got before Query Deconstructor's
    fan-out started firing
  - which chunks appear in one path but not the other

Judgment is still human: read the "only in fan-out" chunks and decide whether
they cover a sub-intent the single-question path missed (the architecture's
stated failure mode -- one averaged embedding for a 3-intent question).
Real per-call cost: one Deconstructor call + N+1 retrieval calls per query
(embedding only, no generation) -- cheap, no answer_generator calls made.

READ-ONLY. Issues no writes beyond the routine agent_steps trace rows
run_agent/retrieve already record for any real call.

Usage:
    py scripts/hand_check_deconstructor_fanout.py --local
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

from audit.logger import start_run
from rag.agents import manager as mgr
from rag.agents.deconstructor import deconstruct
from rag.retriever import retrieve_with_project

TOP_K = 5

# Genuinely compound queries covering topics already known to have corpus
# coverage (per the standard 7-query RAGAs eval set), so a miss is
# meaningful and not just "no documents for this topic."
COMPOUND_QUERIES: tuple[str, ...] = (
    "What are the setback and height limits for a garage in Plano, and do I "
    "need an electrical permit?",
    "Do I need a permit for a bathroom remodel in Dallas, and what are the "
    "ADA requirements for accessibility?",
    "What is the stormwater management requirement in Fort Worth, and is "
    "there a separate fire sprinkler requirement?",
)


def _state(query: str, sub_questions: list[Any]) -> mgr._PlanState:
    """Build a real _PlanState so retrieval calls go through the actual
    manager.py functions, not a hand-copied reimplementation of them."""
    state = mgr._PlanState(
        request=mgr.ManagerRequest(query=query, top_k=TOP_K),
        deps=mgr.ManagerDeps(retrieve=retrieve_with_project),
        store=mgr.ArtifactStore(),
        governor=mgr.BudgetGovernor(),
    )
    state.sub_questions = sub_questions
    return state


def _fanout(query: str, sub_questions: list[Any]) -> list[dict[str, Any]]:
    """The real rag.agents.manager._fanout_retrieval, not a copy of it."""
    result = mgr._fanout_retrieval(_state(query, sub_questions))
    return result.chunks if result is not None else []


def _single(query: str) -> list[dict[str, Any]]:
    """The real rag.agents.manager._single_retrieval, not a copy of it."""
    return mgr._single_retrieval(_state(query, [])).chunks


def _describe(chunks: list[dict[str, Any]]) -> list[str]:
    """One display line per chunk: doc id, similarity score, a text snippet."""
    lines = []
    for c in chunks:
        score = c.get("similarity") or 0.0
        doc = c.get("doc_id") or "?"
        snippet = (c.get("content") or "")[:80].replace("\n", " ")
        lines.append(f"  [{score:.3f}] {doc} — {snippet!r}")
    return lines


def main() -> None:
    """Run each compound query both ways and print the comparison."""
    _db_target.banner(TARGET)

    for query in COMPOUND_QUERIES:
        print("=" * 78)
        print(f"QUERY: {query}\n")

        with start_run("hand_check_deconstructor_fanout"):
            deconstruction = deconstruct(query)

        if not deconstruction.is_compound:
            print("  Deconstructor did NOT split this — treated as single-question.")
            print("  (Check the heuristic in deconstructor.py's _COMPOUND_RE, or the")
            print("   model call itself, if you expected a split here.)\n")
            continue

        print(f"Sub-questions ({len(deconstruction.sub_questions)}):")
        for sq in deconstruction.sub_questions:
            print(f"  - {sq.text!r} (municipality={sq.municipality}, permit_type={sq.permit_type})")

        fanout_chunks = _fanout(query, deconstruction.sub_questions)
        single_chunks = _single(query)

        fanout_ids = {c.get("id") for c in fanout_chunks}
        single_ids = {c.get("id") for c in single_chunks}

        print(f"\nFan-out retrieval ({len(fanout_chunks)} chunks):")
        for line in _describe(fanout_chunks):
            print(line)

        print(f"\nSingle-question retrieval ({len(single_chunks)} chunks):")
        for line in _describe(single_chunks):
            print(line)

        only_fanout = [c for c in fanout_chunks if c.get("id") not in single_ids]
        only_single = [c for c in single_chunks if c.get("id") not in fanout_ids]

        print(f"\nOnly in fan-out ({len(only_fanout)}):")
        for line in _describe(only_fanout):
            print(line)
        print(f"Only in single-question ({len(only_single)}):")
        for line in _describe(only_single):
            print(line)
        print()

    print("=" * 78)
    print("Read the 'only in fan-out' chunks for each query: do they cover a")
    print("sub-intent (e.g. the electrical permit half of a setback+electrical")
    print("question) that 'only in single-question' does not? That's the")
    print("architecture's stated win. If fan-out's extra chunks look irrelevant")
    print("or duplicate the single-question set, that's a sign fan-out isn't")
    print("earning its cost for that query shape.")


if __name__ == "__main__":
    main()
