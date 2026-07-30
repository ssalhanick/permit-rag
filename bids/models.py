"""
bids/models.py — the BidDocument shape docs/agent_architecture.md's Bid
Evaluator (agent #16) was designed around.

`from_marketplace_bid` adapts native marketplace bid rows into it.
`from_pdf_extraction` is a documented, not-built seam: a future chat-uploaded
bid (ingestion/chunker.py + messages.parse against this same schema) would
populate a BidDocument the identical way, so bids/evaluator.py never needs to
know which path produced one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class BidLineItem:
    """One priced scope item within a bid."""

    description: str
    quantity: float
    unit: str
    unit_price: float
    labor_amount: float = 0.0
    material_amount: float = 0.0
    labor_hours: float | None = None
    canonical_work_item: str | None = None


@dataclass(frozen=True)
class BidDocument:
    """A contractor bid, structured for the Bid Evaluator's three analyses."""

    bid_id: str
    project_id: str
    contractor_name: str
    trade: str
    license_number: str
    license_expiration: date | None
    insurance_provider: str | None
    insurance_expiration: date | None
    line_items: tuple[BidLineItem, ...]
    total_price: float
    allowances: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
    payment_schedule: tuple[dict[str, Any], ...]
    permit_responsibility: str | None
    timeline_start: date | None
    timeline_end: date | None
    warranty_text: str | None
    warranty_years: float | None
    change_order_terms: str | None
    lien_waiver_included: bool
    notes: str | None = None


def from_marketplace_bid(
    bid_row: dict[str, Any],
    line_item_rows: list[dict[str, Any]],
    license_row: dict[str, Any],
    contractor_name: str,
) -> BidDocument:
    """Adapt bids + bid_line_items + contractor_licenses rows into a BidDocument."""
    return BidDocument(
        bid_id=str(bid_row["id"]),
        project_id=str(bid_row["project_id"]),
        contractor_name=contractor_name,
        trade=license_row.get("trade", ""),
        license_number=license_row.get("license_number", ""),
        license_expiration=license_row.get("expiration_date"),
        insurance_provider=license_row.get("insurance_provider"),
        insurance_expiration=license_row.get("insurance_expiration_date"),
        line_items=tuple(
            BidLineItem(
                description=li["description"],
                quantity=float(li["quantity"]),
                unit=li["unit"],
                unit_price=float(li["unit_price"]),
                labor_amount=float(li.get("labor_amount") or 0),
                material_amount=float(li.get("material_amount") or 0),
                labor_hours=float(li["labor_hours"]) if li.get("labor_hours") is not None else None,
                canonical_work_item=li.get("canonical_work_item"),
            )
            for li in line_item_rows
        ),
        total_price=float(bid_row["total_price"]),
        allowances=tuple(bid_row.get("allowances") or []),
        exclusions=tuple(bid_row.get("exclusions") or []),
        payment_schedule=tuple(bid_row.get("payment_schedule") or []),
        permit_responsibility=bid_row.get("permit_responsibility"),
        timeline_start=bid_row.get("timeline_start"),
        timeline_end=bid_row.get("timeline_end"),
        warranty_text=bid_row.get("warranty_text"),
        warranty_years=float(bid_row["warranty_years"]) if bid_row.get("warranty_years") is not None else None,
        change_order_terms=bid_row.get("change_order_terms"),
        lien_waiver_included=bool(bid_row.get("lien_waiver_included")),
        notes=bid_row.get("notes"),
    )


# from_pdf_extraction(...) -> BidDocument: NOT built in this pass. Would parse
# an uploaded PDF/image/spreadsheet (ingestion/chunker.py + messages.parse)
# into this same schema for the hiring_contractor persona's "Bid uploads route
# to the Bid Evaluator" chat flow. See docs/agent_architecture.md, agent #16.
