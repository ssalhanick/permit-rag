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
  - the chunks retrieved via fan-out (one retrieval per sub-question, merged
    and re-ranked -- mirrors _fanout_retrieval's own merge logic exactly)
  - the chunks retrieved via the single-question path (today's un-deconstructed
    default -- what every query got before this fix)
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


def _fanout(query: str, sub_questions: list[Any]) -> list[dict[str, Any]]:
    """Mirror rag/agents/manager.py::_fanout_retrieval exactly."""
    merged: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for sub in sub_questions:
        res = retrieve_with_project(
            sub.text, top_k=TOP_K, municipality=sub.municipality,
        )
        for c in res.chunks:
            cid = c.get("id")
            if cid not in seen:
                seen.add(cid)
                merged.append(c)
    merged.sort(key=lambda c: c.get("reranked_score") or c.get("similarity") or 0.0, reverse=True)
    return merged[:TOP_K]


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
        single_result = retrieve_with_project(query, top_k=TOP_K)
        single_chunks = single_result.chunks

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
