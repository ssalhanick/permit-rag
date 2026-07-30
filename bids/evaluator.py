"""
bids/evaluator.py — orchestrates the three Bid Evaluator analyses
(docs/agent_architecture.md, agent #16) against any BidDocument, whether it
came from a native marketplace bid or, eventually, a parsed PDF upload.

Registered into rag/agents/registry.py via api/main.py's DI pattern under
AGENT_NAME, so a future chat-uploaded-bid flow (the hiring_contractor
persona's "Bid uploads route to the Bid Evaluator") can call the identical
evaluator with zero registry changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from bids.completeness import CompletenessResult, check_completeness
from bids.models import BidDocument
from bids.pricing import LinePriceAssessment, assess_price_reasonableness
from bids.red_flags import RedFlag, check_red_flags

AGENT_NAME = "bid_evaluator"

# Disclaimer pattern modeled on _AHJ_DISCLAIMER_TEXT (api/routes/query.py:44),
# per agent_architecture.md's explicit instruction for this agent.
DISCLAIMER = (
    "Estimates only, not legal or financial advice — verify licensing, "
    "insurance, and pricing independently before awarding a bid."
)


class _NovelFlag(BaseModel):
    label: str = Field(..., description="Short name for the flag")
    detail: str = Field(..., description="One sentence explaining the concern")


class _NovelFlagsResponse(BaseModel):
    flags: list[_NovelFlag] = Field(default_factory=list)


_NOVEL_FLAGS_SYSTEM = (
    "You review a contractor's bid on a home-improvement project for a homeowner "
    "marketplace. A deterministic rule table has already checked for the common "
    "red flags (missing license, high deposit, no lien waiver, unassigned permit "
    "responsibility, allowances hiding scope, timeline outliers, missing "
    "insurance). Your only job is to flag genuinely NOVEL concerns the rule "
    "table would not catch — contradictory terms, vague scope language, unusual "
    "exclusions, anything a careful reviewer would ask about. Do not repeat "
    "anything the rule table already covers. If there is nothing novel, return "
    "an empty list. Never invent facts not present in the bid text below."
)


@dataclass(frozen=True)
class BidEvaluationReport:
    bid_id: str
    completeness: CompletenessResult
    red_flags: tuple[RedFlag, ...]
    price_assessments: tuple[LinePriceAssessment, ...]
    llm_flags: tuple[dict[str, str], ...]
    disclaimer: str = DISCLAIMER


def _build_novel_flags_prompt(bid: BidDocument, known_flag_keys: set[str]) -> str:
    lines = [
        f"Contractor: {bid.contractor_name}",
        f"Total price: ${bid.total_price:,.2f}",
        f"Line items: {[li.description for li in bid.line_items]}",
        f"Allowances: {list(bid.allowances)}",
        f"Exclusions: {list(bid.exclusions)}",
        f"Payment schedule: {list(bid.payment_schedule)}",
        f"Warranty: {bid.warranty_text or '(none stated)'}",
        f"Change-order terms: {bid.change_order_terms or '(none stated)'}",
        f"Notes: {bid.notes or '(none)'}",
        f"Already-flagged concerns (do not repeat): {sorted(known_flag_keys) or '(none)'}",
    ]
    return "\n".join(lines)


def _run_llm_novel_flags(bid: BidDocument, known_flag_keys: set[str]) -> list[dict[str, str]]:
    """Best-effort LLM pass for concerns outside the deterministic rule table.

    Never blocks bid submission — any failure (budget, autonomy, API error)
    just yields an empty list rather than propagating.
    """
    try:
        from rag.agent_runtime import Tier, run_agent

        result = run_agent(
            AGENT_NAME,
            system=_NOVEL_FLAGS_SYSTEM,
            messages=[{"role": "user", "content": _build_novel_flags_prompt(bid, known_flag_keys)}],
            tier=Tier.CHEAP,
            output_format=_NovelFlagsResponse,
            max_tokens=512,
            temperature=0.0,
        )
        parsed = result.parsed_output
        if not parsed:
            return []
        return [{"label": f.label, "detail": f.detail} for f in parsed.flags]
    except Exception:
        return []


def evaluate_bid(
    bid: BidDocument,
    *,
    comparison_bids: list[BidDocument] | None = None,
    zip_code: str = "75034",
    run_llm_pass: bool = True,
) -> BidEvaluationReport:
    """Run completeness + red flags + price-reasonableness, plus one optional
    LLM pass for novel red flags beyond the deterministic rule table."""
    completeness = check_completeness(bid)
    red_flags = check_red_flags(bid, comparison_bids=comparison_bids)
    price_assessments = assess_price_reasonableness(bid, zip_code=zip_code)

    llm_flags: list[dict[str, str]] = []
    if run_llm_pass:
        known_keys = {f.key for f in red_flags}
        llm_flags = _run_llm_novel_flags(bid, known_keys)

    return BidEvaluationReport(
        bid_id=bid.bid_id,
        completeness=completeness,
        red_flags=tuple(red_flags),
        price_assessments=tuple(price_assessments),
        llm_flags=tuple(llm_flags),
    )
