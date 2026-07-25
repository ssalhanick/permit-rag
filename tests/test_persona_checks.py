"""
tests/test_persona_checks.py — deterministic persona-appropriateness checks.

These are the cheap middle layer between RAGAs faithfulness (objective floor)
and the Phase 5 LLM judge (subjective quality): does a persona's answer carry the
structural elements its playbook promises? Blunt string matching, no API key.
"""

from __future__ import annotations

from evaluation.persona_checks import (
    check_persona_appropriateness,
    expected_markers,
    persona_appropriateness_score,
)


def test_hiring_contractor_needs_questions_and_red_flags() -> None:
    good = (
        "The permit must be pulled by your contractor.\n"
        "Questions to ask your contractor: who pulls the permit?\n"
        "Red flags to watch for: cash-only, no license."
    )
    assert persona_appropriateness_score("hiring_contractor", good) == 1.0
    assert all(check_persona_appropriateness("hiring_contractor", good).values())


def test_hiring_contractor_missing_red_flags_scores_partial() -> None:
    partial = "Questions to ask your contractor: who pulls the permit?"
    results = check_persona_appropriateness("hiring_contractor", partial)
    assert results["questions_to_ask"] is True
    assert results["red_flags"] is False
    assert persona_appropriateness_score("hiring_contractor", partial) == 0.5


def test_diy_needs_steps_and_a_safety_caveat() -> None:
    good = (
        "Step 1: shut off power. Next, remove the cover.\n"
        "Do not touch the service panel — that is licensed-electrician work."
    )
    assert persona_appropriateness_score("diy", good) == 1.0


def test_unknown_persona_has_nothing_to_check() -> None:
    assert check_persona_appropriateness("wizard", "anything") == {}
    assert persona_appropriateness_score("wizard", "anything") == 1.0
    assert expected_markers("wizard") == ()


def test_expected_markers_are_declared_for_hiring_contractor() -> None:
    assert set(expected_markers("hiring_contractor")) == {"questions_to_ask", "red_flags"}
