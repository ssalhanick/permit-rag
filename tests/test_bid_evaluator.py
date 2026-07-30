"""
tests/test_bid_evaluator.py — completeness, red-flag, price-reasonableness,
and evaluate_bid orchestration. Pure-function, no DB — same style as
tests/test_ontology.py. The two legs that would otherwise touch Postgres/the
network (labor-rate lookup, SerpApi search) are monkeypatched at the
bids.pricing module boundary rather than skipped.
"""

from __future__ import annotations

from datetime import date

import bids.pricing as pricing_module
from bids.completeness import check_completeness
from bids.evaluator import evaluate_bid
from bids.models import BidDocument, BidLineItem
from bids.pricing import assess_price_reasonableness
from bids.red_flags import check_red_flags


def _bid(**overrides) -> BidDocument:
    """A complete, clean bid — every required_clauses.py check passes and no
    red flag fires. Individual tests override just the field under test."""
    defaults = dict(
        bid_id="b1",
        project_id="p1",
        contractor_name="Acme Roofing",
        trade="Roofing",
        license_number="TX12345",
        license_expiration=date(2028, 1, 1),
        insurance_provider="Acme Insurance",
        insurance_expiration=date(2028, 1, 1),
        line_items=(
            BidLineItem("Reroof", 2000, "sq_ft", 5.5, labor_amount=6000, material_amount=5000, labor_hours=80),
        ),
        total_price=11000,
        allowances=(),
        exclusions=(),
        payment_schedule=({"milestone": "deposit", "percent": 20},),
        permit_responsibility="contractor",
        timeline_start=date(2026, 9, 1),
        timeline_end=date(2026, 9, 10),
        warranty_text="5 year warranty",
        warranty_years=5,
        change_order_terms="All change orders must be written and signed.",
        lien_waiver_included=True,
        notes=None,
    )
    defaults.update(overrides)
    return BidDocument(**defaults)


# ── completeness ──────────────────────────────────────────────────


def test_completeness_full_bid_scores_perfect() -> None:
    result = check_completeness(_bid())
    assert result.score == 1.0
    assert result.missing == ()


def test_completeness_flags_each_missing_clause() -> None:
    result = check_completeness(_bid(warranty_text=None, lien_waiver_included=False))
    assert result.score < 1.0
    assert "Warranty terms" in result.missing
    assert "Lien-waiver language" in result.missing


def test_completeness_missing_timeline_when_either_bound_absent() -> None:
    result = check_completeness(_bid(timeline_end=None))
    assert "Timeline" in result.missing


# ── red flags ─────────────────────────────────────────────────────


def test_red_flags_clean_bid_has_none() -> None:
    assert check_red_flags(_bid()) == []


def test_red_flags_missing_license_and_insurance() -> None:
    flags = check_red_flags(_bid(license_number="", insurance_provider=None))
    keys = {f.key for f in flags}
    assert "missing_license" in keys
    assert "no_insurance_cert" in keys


def test_red_flags_high_deposit_over_texas_norm() -> None:
    flags = check_red_flags(_bid(payment_schedule=({"milestone": "deposit", "percent": 60},)))
    assert any(f.key == "high_deposit" for f in flags)


def test_red_flags_deposit_within_norm_not_flagged() -> None:
    flags = check_red_flags(_bid(payment_schedule=({"milestone": "deposit", "percent": 25},)))
    assert not any(f.key == "high_deposit" for f in flags)


def test_red_flags_no_lien_waiver() -> None:
    flags = check_red_flags(_bid(lien_waiver_included=False))
    assert any(f.key == "no_lien_waiver" for f in flags)


def test_red_flags_permit_responsibility_unassigned() -> None:
    flags = check_red_flags(_bid(permit_responsibility=None))
    assert any(f.key == "permit_responsibility_unassigned" for f in flags)


def test_red_flags_allowances_hide_scope() -> None:
    flags = check_red_flags(_bid(allowances=({"description": "fixtures", "amount": 5000},)))
    assert any(f.key == "allowances_hide_scope" for f in flags)


def test_red_flags_verbal_change_orders_keyword_heuristic() -> None:
    flags = check_red_flags(_bid(change_order_terms="Verbal agreement is fine."))
    assert any(f.key == "verbal_change_orders" for f in flags)


def test_red_flags_written_change_orders_not_flagged() -> None:
    flags = check_red_flags(_bid(change_order_terms="Must be written and signed by both parties."))
    assert not any(f.key == "verbal_change_orders" for f in flags)


def test_red_flags_cash_only_discount_keyword_heuristic() -> None:
    flags = check_red_flags(_bid(notes="10% discount for cash payment."))
    assert any(f.key == "cash_only_discount" for f in flags)


def test_red_flags_timeline_outlier_vs_comparison_bids() -> None:
    typical = [_bid(bid_id=f"other-{i}", timeline_start=date(2026, 9, 1), timeline_end=date(2026, 9, 10)) for i in range(3)]
    outlier = _bid(bid_id="outlier", timeline_start=date(2026, 9, 1), timeline_end=date(2027, 3, 1))
    flags = check_red_flags(outlier, comparison_bids=typical + [outlier])
    assert any(f.key == "timeline_outlier" for f in flags)


def test_red_flags_typical_timeline_not_flagged_as_outlier() -> None:
    bids_on_project = [_bid(bid_id=f"b{i}", timeline_start=date(2026, 9, 1), timeline_end=date(2026, 9, 10 + i)) for i in range(3)]
    flags = check_red_flags(bids_on_project[0], comparison_bids=bids_on_project)
    assert not any(f.key == "timeline_outlier" for f in flags)


# ── price reasonableness (DB/network calls monkeypatched) ─────────


def test_price_reasonableness_labor_in_range(monkeypatch) -> None:
    monkeypatch.setattr(
        pricing_module, "get_labor_rate_benchmark",
        lambda trade, region="DFW": {"low_hourly_rate": 50, "high_hourly_rate": 90},
    )
    monkeypatch.setattr(pricing_module, "search_home_depot", lambda query, *, zip_code, limit: [])

    bid = _bid(line_items=(
        BidLineItem("Reroof", 2000, "sq_ft", 5.5, labor_amount=6000, material_amount=0, labor_hours=80),
    ))
    assessments = assess_price_reasonableness(bid)
    labor = [a for a in assessments if a.signal.startswith("labor")]
    assert len(labor) == 1
    assert labor[0].signal == "labor_in_range"


def test_price_reasonableness_labor_high_flags_above_range(monkeypatch) -> None:
    monkeypatch.setattr(
        pricing_module, "get_labor_rate_benchmark",
        lambda trade, region="DFW": {"low_hourly_rate": 50, "high_hourly_rate": 90},
    )
    monkeypatch.setattr(pricing_module, "search_home_depot", lambda query, *, zip_code, limit: [])

    bid = _bid(line_items=(
        BidLineItem("Reroof", 2000, "sq_ft", 5.5, labor_amount=16000, material_amount=0, labor_hours=80),
    ))
    assessments = assess_price_reasonableness(bid)
    assert any(a.signal == "labor_high" for a in assessments)


def test_price_reasonableness_material_high_vs_cheapest_comparable(monkeypatch) -> None:
    monkeypatch.setattr(pricing_module, "get_labor_rate_benchmark", lambda trade, region="DFW": None)
    monkeypatch.setattr(
        pricing_module, "search_home_depot",
        lambda query, *, zip_code, limit: [{"price": 1.0}, {"price": 1.5}],
    )

    bid = _bid(line_items=(
        BidLineItem("Subway tile", 500, "sq_ft", 5.0, labor_amount=0, material_amount=2500, labor_hours=None),
    ))
    assessments = assess_price_reasonableness(bid)
    material = [a for a in assessments if a.signal.startswith("material")]
    assert len(material) == 1
    assert material[0].signal == "material_high"


def test_price_reasonableness_no_labor_hours_skips_labor_assessment(monkeypatch) -> None:
    monkeypatch.setattr(pricing_module, "get_labor_rate_benchmark", lambda trade, region="DFW": None)
    monkeypatch.setattr(pricing_module, "search_home_depot", lambda query, *, zip_code, limit: [])

    bid = _bid(line_items=(
        BidLineItem("Reroof", 2000, "sq_ft", 5.5, labor_amount=6000, material_amount=0, labor_hours=None),
    ))
    assessments = assess_price_reasonableness(bid)
    assert not any(a.signal.startswith("labor") for a in assessments)


# ── evaluate_bid orchestration ──────────────────────────────────────


def test_evaluate_bid_combines_all_legs_without_llm_pass(monkeypatch) -> None:
    monkeypatch.setattr(pricing_module, "get_labor_rate_benchmark", lambda trade, region="DFW": None)
    monkeypatch.setattr(pricing_module, "search_home_depot", lambda query, *, zip_code, limit: [])

    bid = _bid(lien_waiver_included=False)  # forces one deterministic red flag + one completeness gap
    report = evaluate_bid(bid, run_llm_pass=False)

    assert report.bid_id == "b1"
    assert report.completeness.score < 1.0
    assert any(f.key == "no_lien_waiver" for f in report.red_flags)
    assert report.llm_flags == ()
    assert "not legal or financial advice" in report.disclaimer


def test_evaluate_bid_llm_pass_failure_degrades_gracefully(monkeypatch) -> None:
    """A broken/unavailable LLM call must never break evaluation — llm_flags
    just comes back empty, and no exception propagates out of evaluate_bid."""
    monkeypatch.setattr(pricing_module, "get_labor_rate_benchmark", lambda trade, region="DFW": None)
    monkeypatch.setattr(pricing_module, "search_home_depot", lambda query, *, zip_code, limit: [])

    import rag.agent_runtime as agent_runtime_module

    def _boom(*args, **kwargs):
        raise RuntimeError("no API key in this environment")

    monkeypatch.setattr(agent_runtime_module, "run_agent", _boom)

    report = evaluate_bid(_bid(), run_llm_pass=True)
    assert report.llm_flags == ()
