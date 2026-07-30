"""
tests/test_generator_clarification_fallback.py — clarification fallback reads
live coverage instead of a hardcoded city list.

Regression guard: the old hardcoded list included Frisco and McKinney, which
are seeded jurisdictions with zero real ingested documents — this actively
steered users toward two cities with no actual content.
"""

from __future__ import annotations

from unittest.mock import patch

from rag.generator import generate_clarification_fallback


@patch("rag.coverage.covered_municipalities", return_value=["Dallas", "Plano", "Fort Worth"])
def test_static_fallback_uses_live_covered_municipalities(_mock_covered, monkeypatch) -> None:
    """With no LLM provider configured, the static fallback's choices must come
    from rag.coverage, not a hardcoded literal."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    result = generate_clarification_fallback("What permit do I need for a fence?")

    jurisdiction_option = result["clarifying_options"][0]
    assert jurisdiction_option["choices"] == ["Dallas", "Plano", "Fort Worth"]
    assert "Frisco" not in jurisdiction_option["choices"]
    assert "McKinney" not in jurisdiction_option["choices"]


def test_clarification_system_prompt_omits_uncovered_cities() -> None:
    """The LLM-facing system prompt's illustrative example must also stay accurate."""
    from rag.generator import _clarification_system_prompt

    with patch("rag.coverage.covered_municipalities", return_value=["Dallas", "Plano", "Fort Worth"]):
        prompt = _clarification_system_prompt()

    assert '"Dallas"' in prompt
    assert "Frisco" not in prompt
    assert "McKinney" not in prompt
