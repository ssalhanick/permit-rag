"""
bids/red_flags.py — deterministic red-flag rule table (docs/agent_architecture.md,
Bid Evaluator agent #16).

7 of the 9 named flags are cleanly deterministic against the BidDocument
schema. The remaining 2 (verbal change orders, cash-only discount) are
keyword heuristics here — weaker signal, real false-negative risk — which is
exactly where bids/evaluator.py's LLM-assisted "novel flags" pass earns its
keep instead of being a catch-all for everything.

The timeline-outlier check is enabled specifically by the marketplace
context: comparable bids on the *same project* are sitting in the same
table, an improvement over the original PDF-upload-only design where no
comparable existed.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from bids.models import BidDocument

# Texas norm per docs/agent_architecture.md: a 10-33% deposit is typical.
_DEPOSIT_PCT_WARN_THRESHOLD = 50.0
_ALLOWANCE_SHARE_WARN_THRESHOLD = 0.30  # allowances > 30% of total price


@dataclass(frozen=True)
class RedFlag:
    key: str
    severity: str  # "high" | "medium" | "low"
    message: str


def _deposit_percent(bid: BidDocument) -> float | None:
    """Best-effort deposit percent from a payment_schedule entry tagged as a deposit."""
    for entry in bid.payment_schedule:
        label = str(entry.get("milestone", "")).lower()
        if "deposit" not in label and "upfront" not in label:
            continue
        pct = entry.get("percent")
        if pct is not None:
            return float(pct)
        amount = entry.get("amount")
        if amount is not None and bid.total_price:
            return float(amount) / bid.total_price * 100
    return None


def _allowance_share(bid: BidDocument) -> float:
    total_allowances = sum(float(a.get("amount") or 0) for a in bid.allowances)
    if not bid.total_price:
        return 0.0
    return total_allowances / bid.total_price


def _timeline_days(bid: BidDocument) -> int | None:
    if bid.timeline_start and bid.timeline_end:
        return (bid.timeline_end - bid.timeline_start).days
    return None


def check_red_flags(bid: BidDocument, *, comparison_bids: list[BidDocument] | None = None) -> list[RedFlag]:
    """Run all deterministic + keyword-heuristic checks against one bid."""
    flags: list[RedFlag] = []

    if not bid.license_number:
        flags.append(RedFlag("missing_license", "high", "No license number on file for this bid."))
    if not bid.insurance_provider:
        flags.append(RedFlag("no_insurance_cert", "high", "No insurance certificate on file for this bid."))

    deposit_pct = _deposit_percent(bid)
    if deposit_pct is not None and deposit_pct > _DEPOSIT_PCT_WARN_THRESHOLD:
        flags.append(RedFlag(
            "high_deposit", "medium",
            f"Deposit is {deposit_pct:.0f}% of total — above the ~10-33% Texas norm.",
        ))

    if not bid.lien_waiver_included:
        flags.append(RedFlag("no_lien_waiver", "medium", "Bid does not include lien-waiver language."))

    if bid.permit_responsibility is None:
        flags.append(RedFlag(
            "permit_responsibility_unassigned", "medium",
            "Bid does not state who is responsible for pulling permits.",
        ))

    if _allowance_share(bid) > _ALLOWANCE_SHARE_WARN_THRESHOLD:
        flags.append(RedFlag(
            "allowances_hide_scope", "medium",
            "Allowances make up a large share of the total price, which can hide scope until later.",
        ))

    this_duration = _timeline_days(bid)
    if comparison_bids and this_duration is not None:
        durations = []
        for other in comparison_bids:
            if other.bid_id == bid.bid_id:
                continue
            other_duration = _timeline_days(other)
            if other_duration is not None:
                durations.append(other_duration)
        if durations:
            typical = median(durations)
            if typical > 0 and (this_duration < typical * 0.4 or this_duration > typical * 2.5):
                flags.append(RedFlag(
                    "timeline_outlier", "medium",
                    f"Proposed timeline ({this_duration}d) is far from other bids on this "
                    f"project (typical {typical:.0f}d).",
                ))

    change_terms = (bid.change_order_terms or "").lower()
    if change_terms and "writ" not in change_terms and "sign" not in change_terms:
        flags.append(RedFlag(
            "verbal_change_orders", "low",
            "Change-order terms don't clearly require written/signed approval "
            "(keyword check only — verify manually).",
        ))

    haystack = f"{bid.notes or ''} " + " ".join(str(e) for e in bid.payment_schedule)
    haystack = haystack.lower()
    if "cash" in haystack and "discount" in haystack:
        flags.append(RedFlag(
            "cash_only_discount", "low",
            "Mentions a cash-only discount (keyword check only — verify manually).",
        ))

    return flags
