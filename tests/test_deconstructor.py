"""
tests/test_deconstructor.py — Query Deconstructor (agent #5)
===========================================================
The deterministic gate decides whether the model is called at all; the compound
path is exercised with a mocked ``run_agent``.
"""

from __future__ import annotations

from types import SimpleNamespace

from rag.agents import deconstructor as dc
from rag.agents.deconstructor import Deconstruction, SubQuestion, deconstruct


def test_simple_query_is_single_no_llm(monkeypatch) -> None:
    """A one-intent query returns a single sub-question without calling the model."""
    def _boom(*_a, **_k):
        raise AssertionError("run_agent must not be called for a simple query")

    monkeypatch.setattr(dc, "run_agent", _boom)
    result = deconstruct("What is the fence setback in Dallas?")
    assert result.is_compound is False
    assert result.sub_questions[0].text == "What is the fence setback in Dallas?"


def test_empty_query_yields_no_sub_questions() -> None:
    """Blank input produces an empty deconstruction, no crash."""
    assert deconstruct("   ").sub_questions == []


def test_compound_query_calls_model(monkeypatch) -> None:
    """A conjunction-bearing query is split by the (mocked) structured call."""
    fake = Deconstruction(sub_questions=[
        SubQuestion(text="What is the setback for a garage in Plano?", municipality="plano"),
        SubQuestion(text="Do I need an electrical permit?", permit_type="electrical"),
    ])
    monkeypatch.setattr(dc, "run_agent", lambda *a, **k: SimpleNamespace(parsed_output=fake))
    result = deconstruct("Setback for a garage in Plano, and do I need an electrical permit?")
    assert result.is_compound is True
    assert result.sub_questions[1].permit_type == "electrical"


def test_use_llm_false_stays_single_even_if_compound(monkeypatch) -> None:
    """--no-llm callers get the single form regardless of surface shape."""
    def _boom(*_a, **_k):
        raise AssertionError("run_agent must not be called with use_llm=False")

    monkeypatch.setattr(dc, "run_agent", _boom)
    result = deconstruct("A and B and C", use_llm=False)
    assert result.is_compound is False


def test_model_failure_degrades_to_single(monkeypatch) -> None:
    """If the model errors, the compound query still returns a usable single form."""
    def _boom(*_a, **_k):
        raise RuntimeError("model down")

    monkeypatch.setattr(dc, "run_agent", _boom)
    result = deconstruct("setbacks and heights and permits, oh my")
    assert result.is_compound is False
    assert result.sub_questions[0].text.startswith("setbacks and heights")


def test_empty_model_output_degrades_to_single(monkeypatch) -> None:
    """A model that returns zero sub-questions falls back to the single form."""
    empty = Deconstruction(sub_questions=[])
    monkeypatch.setattr(dc, "run_agent", lambda *a, **k: SimpleNamespace(parsed_output=empty))
    result = deconstruct("this and that")
    assert len(result.sub_questions) == 1
