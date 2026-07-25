"""
evaluation/persona_checks.py — deterministic persona-appropriateness checks
===========================================================================
Phase 4 ships the fragment library; the *objective* faithfulness gate (RAGAs)
and the *subjective* LLM-judge persona metric (the Evaluator, agent #23) frame
the two ends of prompt quality. Between them sits a cheap, deterministic middle:
does a persona's answer contain the structural elements its playbook promises?

These are surface checks, not judgments — a ``hiring_contractor`` answer must
carry a "red flags" and a "questions to ask" section; a ``diy`` answer must show
steps and a safety caveat. They cost nothing (string matching), run in unit
tests without an API key, and catch the blunt regression where a persona
fragment silently stops shaping the answer. The nuanced "is this actually good
for a DIYer?" question is the Evaluator's LLM judge in Phase 5.

Import boundary: evaluation/ → rag/, db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import re

# Each check is (label, regex) — case-insensitive, matched against the answer.
_PERSONA_EXPECTATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "hiring_contractor": (
        ("questions_to_ask", r"question"),
        ("red_flags", r"red flag"),
    ),
    "diy": (
        ("steps", r"step|first|next|then\b"),
        ("safety", r"safety|licensed|do not|should not|professional"),
    ),
    "contractor": (
        ("citation", r"\[[^\]]+chunk\s*\d+\]"),
    ),
    "research": (
        ("citation", r"\[[^\]]+chunk\s*\d+\]"),
    ),
}


def expected_markers(persona: str) -> tuple[str, ...]:
    """Return the marker labels a persona's answer should contain."""
    return tuple(label for label, _ in _PERSONA_EXPECTATIONS.get(persona, ()))


def check_persona_appropriateness(persona: str, answer: str) -> dict[str, bool]:
    """Return ``{marker: present}`` for each structural element a persona expects.

    Unknown personas return an empty dict (nothing to check). Presence is a
    deterministic string/regex match — deliberately blunt, so a green result
    means "the fragment shaped the answer at all", not "the answer is good".
    """
    checks = _PERSONA_EXPECTATIONS.get(persona, ())
    text = answer or ""
    return {
        label: re.search(pattern, text, re.IGNORECASE) is not None
        for label, pattern in checks
    }


def persona_appropriateness_score(persona: str, answer: str) -> float:
    """Fraction of a persona's expected markers present (1.0 when none apply)."""
    results = check_persona_appropriateness(persona, answer)
    if not results:
        return 1.0
    return sum(results.values()) / len(results)
