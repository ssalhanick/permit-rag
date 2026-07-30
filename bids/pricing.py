"""
bids/pricing.py — price-reasonableness leg of the Bid Evaluator.

Labor: compares a line item's labor_amount/labor_hours against
labor_rate_benchmarks (migration 043) for the bid's trade, when labor_hours
is present. Materials: resolves each material line item's free-text
description against commerce/serpapi_client.search_home_depot — the same
pricing source commerce/product_resolver.py already uses for design-intent
overlays — and flags a unit price well above the cheapest comparable found.

No per-line ontology mapping is attempted here; docs/agent_architecture.md
flags that mapping "hard," and BidLineItem.canonical_work_item is the
forward-compat seam for it once it exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from bids.models import BidDocument, BidLineItem
from commerce.serpapi_client import search_home_depot
from db.client import get_labor_rate_benchmark

_MATERIAL_PRICE_RATIO_WARN = 1.5  # flag if unit_price > 1.5x the cheapest comparable found


@dataclass(frozen=True)
class LinePriceAssessment:
    description: str
    signal: str  # labor_in_range | labor_high | labor_low | material_in_range | material_high | no_comparable | not_assessed
    detail: str


def _assess_labor(item: BidLineItem, trade: str) -> LinePriceAssessment | None:
    if not item.labor_hours or item.labor_amount <= 0:
        return None
    benchmark = get_labor_rate_benchmark(trade)
    if not benchmark:
        return LinePriceAssessment(item.description, "not_assessed", f"No labor-rate benchmark seeded for {trade}.")
    rate = item.labor_amount / item.labor_hours
    low, high = float(benchmark["low_hourly_rate"]), float(benchmark["high_hourly_rate"])
    if rate < low:
        return LinePriceAssessment(
            item.description, "labor_low",
            f"${rate:.0f}/hr is below the seeded {trade} range (${low:.0f}-${high:.0f}/hr).",
        )
    if rate > high:
        return LinePriceAssessment(
            item.description, "labor_high",
            f"${rate:.0f}/hr is above the seeded {trade} range (${low:.0f}-${high:.0f}/hr).",
        )
    return LinePriceAssessment(item.description, "labor_in_range", f"${rate:.0f}/hr is within the seeded {trade} range.")


def _assess_material(item: BidLineItem, *, zip_code: str) -> LinePriceAssessment | None:
    if item.material_amount <= 0:
        return None
    try:
        products = search_home_depot(item.description, zip_code=zip_code, limit=3)
    except Exception:
        return LinePriceAssessment(item.description, "not_assessed", "Materials price lookup failed.")
    prices = [p["price"] for p in products if p.get("price") is not None]
    if not prices:
        return LinePriceAssessment(item.description, "no_comparable", "No comparable product found to check pricing against.")
    cheapest = min(prices)
    if cheapest > 0 and item.unit_price > cheapest * _MATERIAL_PRICE_RATIO_WARN:
        return LinePriceAssessment(
            item.description, "material_high",
            f"${item.unit_price:.2f}/unit is well above the cheapest comparable product found (${cheapest:.2f}).",
        )
    return LinePriceAssessment(
        item.description, "material_in_range",
        f"${item.unit_price:.2f}/unit is near comparable product pricing (from ${cheapest:.2f}).",
    )


def assess_price_reasonableness(bid: BidDocument, *, zip_code: str = "75034") -> list[LinePriceAssessment]:
    """Per-line labor and materials price assessments.

    Best-effort: a failed lookup or missing benchmark for one line never
    blocks assessment of the rest.
    """
    assessments: list[LinePriceAssessment] = []
    for item in bid.line_items:
        labor = _assess_labor(item, bid.trade)
        if labor:
            assessments.append(labor)
        material = _assess_material(item, zip_code=zip_code)
        if material:
            assessments.append(material)
    return assessments
