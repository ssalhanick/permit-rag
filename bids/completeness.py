"""
bids/completeness.py — completeness leg of the Bid Evaluator.

Pure lookup against required_clauses.py. $0, no I/O, no model call.
"""

from __future__ import annotations

from dataclasses import dataclass

from bids.models import BidDocument
from bids.required_clauses import REQUIRED_CLAUSES


@dataclass(frozen=True)
class CompletenessResult:
    score: float  # fraction of required clauses present, 0.0-1.0
    missing: tuple[str, ...]  # labels of missing clauses


def check_completeness(bid: BidDocument) -> CompletenessResult:
    """Checklist against REQUIRED_CLAUSES."""
    missing = tuple(clause.label for clause in REQUIRED_CLAUSES if not clause.present(bid))
    score = (len(REQUIRED_CLAUSES) - len(missing)) / len(REQUIRED_CLAUSES)
    return CompletenessResult(score=round(score, 2), missing=missing)
