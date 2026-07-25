"""
scripts/persona_demo.py — Phase 4 headline demo: one question, three personas.

Runs the SAME query through the Prompt Router as different personas and prints
the three genuinely different answers side by side, with the routing evidence
(fragment ids, persona-aware max_tokens, truncation flag, appropriateness
markers). This is the most legible demonstration of "agents" to a non-technical
audience — a DIYer, a contractor, and someone hiring a contractor asking the
same thing and getting materially different answers.

Read-only against the corpus (retrieval + generation, no DB writes). Needs the
corpus machine (machine B): ANTHROPIC_API_KEY for generation and a reachable
DATABASE_URL for retrieval. Target-safe via scripts/_db_target (never a bare
bootstrap_env — this repo's recurring footgun).

Usage (machine B):
    py scripts/persona_demo.py --local
    py scripts/persona_demo.py --local "Do I need a permit to replace a water heater?" --municipality dallas
    py scripts/persona_demo.py --local --personas diy,hiring_contractor --intent how_to
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

# A query known to retrieve above the grounding floor against the 19-doc corpus
# (it is in the RAGAs/langsmith eval set). A vague query abstains before routing,
# which shows nothing — pick something the corpus actually covers.
_DEFAULT_QUERY = (
    "What permits are needed for a bathroom addition with new electrical "
    "and plumbing in Dallas?"
)
_DEFAULT_PERSONAS = ("diy", "contractor", "hiring_contractor")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI flags. Read-only demo — nothing writes to the corpus."""
    parser = argparse.ArgumentParser(description="Phase 4 persona-routing demo.")
    parser.add_argument("query", nargs="?", default=_DEFAULT_QUERY, help="The question to ask.")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--municipality", default="dallas", help="Jurisdiction scope.")
    parser.add_argument("--personas", default=",".join(_DEFAULT_PERSONAS),
                        help="Comma-separated personas to compare.")
    parser.add_argument("--intent", default=None, help="Force an intent fragment (optional).")
    parser.add_argument("--experience", default=None, help="first_timer | experienced (optional).")
    parser.add_argument("--top-k", type=int, default=10, help="Retrieval top_k.")
    return parser.parse_args(argv)


def _run_one(query: str, persona: str, args: argparse.Namespace) -> dict:
    """Run the pipeline for one persona. Imported lazily so the DB target is fixed first."""
    from evaluation.langsmith_eval import run_pipeline

    return run_pipeline(
        query,
        municipality=args.municipality,
        top_k=args.top_k,
        persona=persona,
        experience=args.experience,
        intent=args.intent,
    )


def _print_one(persona: str, result: dict) -> None:
    """Print one persona's answer with its routing evidence."""
    from evaluation.persona_checks import persona_appropriateness_score
    from rag.agents.prompt_router import max_tokens_for

    intent = "compliance_lookup"
    for frag in result.get("prompt_fragment_ids") or []:
        if frag.startswith("intent:"):
            intent = frag.split(":", 1)[1].split("@", 1)[0]
    answer = result.get("answer") or "(abstained — retrieval below the grounding floor)"
    truncated = result.get("stop_reason") == "max_tokens"
    score = persona_appropriateness_score(persona, answer)

    print("\n" + "=" * 78)
    print(f"PERSONA: {persona}")
    print("-" * 78)
    print(f"  max_tokens (persona/intent): {max_tokens_for(persona, intent)}"
          f"   output_tokens: {result.get('output_tokens')}"
          f"   stop_reason: {result.get('stop_reason')}"
          f"{'   ⚠ TRUNCATED' if truncated else ''}")
    print(f"  fragments: {', '.join(result.get('prompt_fragment_ids') or []) or '(none)'}")
    print(f"  appropriateness markers present: {score:.0%}")
    print("-" * 78)
    print(answer)


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, then run the same query across each persona."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    personas = [p.strip() for p in args.personas.split(",") if p.strip()]

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=True)
    _db_target.ensure_reachable(target)

    print(f'\nQuery: "{args.query}"   (municipality={args.municipality}, top_k={args.top_k})')
    print(f"Comparing personas: {', '.join(personas)}")

    for persona in personas:
        result = _run_one(args.query, persona, args)
        _print_one(persona, result)

    print("\n" + "=" * 78)
    print("Same question, three personas — three genuinely different answers.")
    print("A ⚠ TRUNCATED flag means max_tokens was still too low → Guardrail action item.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
