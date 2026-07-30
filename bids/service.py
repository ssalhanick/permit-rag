"""
bids/service.py — thin orchestration over db/client.py for bid create/list/award.

No SQL here — every existing package in this repo keeps DB access centralized
in db/client.py; bids/ is no exception even though AGENTS.md's import
boundaries permit bids/ -> db/ directly.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from bids.models import BidDocument, from_marketplace_bid
from db import client as db_client


def compute_totals(line_items: list[dict[str, Any]]) -> tuple[float, float, float]:
    """(total_price, labor_total, material_total) derived from line items —
    never trusted from the client."""
    total = 0.0
    labor = 0.0
    material = 0.0
    for item in line_items:
        quantity = float(item["quantity"])
        unit_price = float(item["unit_price"])
        total += quantity * unit_price
        labor += float(item.get("labor_amount") or 0)
        material += float(item.get("material_amount") or 0)
    return round(total, 2), round(labor, 2), round(material, 2)


def create_bid(
    *,
    project_id: UUID,
    contractor_profile_id: UUID,
    license_id: UUID,
    line_items: list[dict[str, Any]],
    **bid_fields: Any,
) -> dict[str, Any]:
    """Server-computes totals from line_items, then persists header + lines."""
    total_price, labor_total, material_total = compute_totals(line_items)
    return db_client.create_bid(
        project_id=project_id,
        contractor_profile_id=contractor_profile_id,
        license_id=license_id,
        total_price=total_price,
        labor_total=labor_total,
        material_total=material_total,
        line_items=line_items,
        **bid_fields,
    )


def build_bid_document(bid_row: dict[str, Any]) -> BidDocument:
    """Assemble a full BidDocument for a bid row: fetches its line items and
    backing license/profile, then adapts via bids.models.from_marketplace_bid."""
    line_items = db_client.list_bid_line_items(bid_row["id"])
    license_row = db_client.get_contractor_license(bid_row["license_id"]) or {}
    profile = db_client.get_contractor_profile(bid_row["contractor_profile_id"]) or {}
    contractor_name = profile.get("business_name", "Unknown contractor")
    return from_marketplace_bid(bid_row, line_items, license_row, contractor_name)


def list_bids_for_project(project_id: UUID) -> list[dict[str, Any]]:
    return db_client.list_bids_for_project(project_id)


def list_bids_for_contractor(contractor_profile_id: UUID) -> list[dict[str, Any]]:
    return db_client.list_bids_for_contractor(contractor_profile_id)


def get_bid(bid_id: UUID) -> dict[str, Any] | None:
    return db_client.get_bid(bid_id)


def withdraw_bid(bid_id: UUID) -> dict[str, Any] | None:
    return db_client.withdraw_bid(bid_id)


def award_bid(project_id: UUID, bid_id: UUID) -> dict[str, Any] | None:
    return db_client.award_bid(project_id, bid_id)
