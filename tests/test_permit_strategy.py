"""
tests/test_permit_strategy.py — Permit Strategy (agent #11)
==========================================================
The permit set must match frontend/src/projectPermitRules.js exactly (the F1
ground truth); sequencing + fees are deterministic. The optional note is mocked.
"""

from __future__ import annotations

from types import SimpleNamespace

from rag.agents import permit_strategy as ps
from rag.agents.permit_strategy import plan_permits, recommend_permits


def test_permit_set_matches_js_rules() -> None:
    """recommend_permits mirrors WORK_TYPE_TO_PERMITS (sorted, deduped)."""
    # Pool/Spa → Building, Zoning, Electrical, Plumbing; Roofing → Building, Roofing.
    assert recommend_permits(["Pool / Spa"]) == ["Building", "Electrical", "Plumbing", "Zoning"]
    assert recommend_permits(["Roofing", "Electrical"]) == ["Building", "Electrical", "Roofing"]
    # Cosmetic-only work needs no permit.
    assert recommend_permits(["Paint / Drywall", "Flooring"]) == []
    assert recommend_permits([]) == []


def test_sequencing_orders_by_pull_rank() -> None:
    """Demolition precedes Building precedes the trade rough-ins precedes Roofing."""
    strat = plan_permits({"work_types": ["Demolition", "Roofing", "Electrical"]}, use_llm=False)
    seq = strat.sequence
    assert seq.index("Demolition") < seq.index("Building") < seq.index("Roofing")
    assert seq.index("Building") < seq.index("Electrical")


def test_fee_estimate_sums_known_permits() -> None:
    """Fees sum the per-permit base estimates; disclaimer is always present."""
    strat = plan_permits({"work_types": ["Electrical", "Plumbing"]}, use_llm=False)
    assert strat.fee_breakdown == {"Electrical": 75, "Plumbing": 75}
    assert strat.estimated_fees_usd == 150
    assert "estimate" in strat.fee_disclaimer.lower()


def test_cosmetic_only_note_no_permits(monkeypatch) -> None:
    """A cosmetic-only scope reports no permits and does not call the model."""
    def _boom(*_a, **_k):
        raise AssertionError("no note call when there are no permits")

    monkeypatch.setattr(ps, "run_agent", _boom)
    strat = plan_permits({"work_types": ["Flooring"]}, use_llm=True)
    assert strat.permits == []
    assert "cosmetic" in strat.notes.lower()


def test_llm_note_used_when_available(monkeypatch) -> None:
    """When the model returns a note, it replaces the template."""
    monkeypatch.setattr(
        ps, "run_agent",
        lambda *a, **k: SimpleNamespace(text="Pull the building permit before the electrical rough-in."),
    )
    strat = plan_permits({"work_types": ["Structural / Framing", "Electrical"], "municipality": "plano"})
    assert strat.notes == "Pull the building permit before the electrical rough-in."


def test_llm_note_failure_falls_back_to_template(monkeypatch) -> None:
    """A note-call failure degrades to the deterministic templated note."""
    def _boom(*_a, **_k):
        raise RuntimeError("model down")

    monkeypatch.setattr(ps, "run_agent", _boom)
    strat = plan_permits({"work_types": ["Electrical"], "municipality": "dallas"})
    assert "dallas" in strat.notes.lower()
    assert "Electrical" in strat.notes
