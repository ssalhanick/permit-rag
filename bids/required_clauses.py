"""
bids/required_clauses.py — the completeness checklist as data, not logic.

Mirrors forms/ontology.py's rationale: git-tracked content that changes with a
code deploy, not runtime data, so it lives in a module rather than a table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from bids.models import BidDocument


@dataclass(frozen=True)
class RequiredClause:
    key: str
    label: str
    present: Callable[[BidDocument], bool]


REQUIRED_CLAUSES: tuple[RequiredClause, ...] = (
    RequiredClause("contractor_identity", "Contractor identity", lambda b: bool(b.contractor_name)),
    RequiredClause("license_number", "License number", lambda b: bool(b.license_number)),
    RequiredClause("line_items", "At least one priced line item", lambda b: len(b.line_items) > 0),
    RequiredClause("payment_schedule", "Payment schedule", lambda b: len(b.payment_schedule) > 0),
    RequiredClause("timeline", "Timeline", lambda b: b.timeline_start is not None and b.timeline_end is not None),
    RequiredClause("warranty", "Warranty terms", lambda b: bool(b.warranty_text)),
    RequiredClause("change_order_terms", "Change-order terms", lambda b: bool(b.change_order_terms)),
    RequiredClause("lien_waiver", "Lien-waiver language", lambda b: b.lien_waiver_included),
    RequiredClause("insurance", "Insurance certificate on file", lambda b: bool(b.insurance_provider)),
)
