"""
api/routes/bids.py — bid submission, listing, withdrawal, and award.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.contractor_auth import require_biddable_contractor, require_contractor_profile
from api.design_intent_helpers import check_bid_evaluation_cap, record_bid_evaluation_usage
from api.schemas import BidResponse, CreateBidRequest
from bids import service as bids_service
from bids.evaluator import evaluate_bid
from commerce.takeoff import extract_zip_from_address
from db import client as db_client

router = APIRouter(tags=["bids"])
CurrentUser = Annotated[dict, Depends(get_current_user)]
BiddableContractor = Annotated[dict, Depends(require_biddable_contractor)]
Contractor = Annotated[dict, Depends(require_contractor_profile)]


def _evaluate(bid_row: dict, *, evaluating_user_id: UUID) -> dict:
    """Run the Bid Evaluator against one bid, comparing it to the project's
    other live bids. The LLM-assisted novel-flags leg is best-effort and
    capped per user — a spent cap degrades to deterministic-only, it never
    blocks the response."""
    document = bids_service.build_bid_document(bid_row)
    project = db_client.get_project(bid_row["project_id"])
    zip_code = extract_zip_from_address((project or {}).get("address")) or "75034"

    other_rows = [
        row for row in db_client.list_bids_for_project(bid_row["project_id"])
        if row["id"] != bid_row["id"] and row["status"] in ("submitted", "awarded")
    ]
    comparison = [bids_service.build_bid_document(row) for row in other_rows]

    run_llm_pass = True
    try:
        check_bid_evaluation_cap(evaluating_user_id)
    except HTTPException:
        run_llm_pass = False

    report = evaluate_bid(document, comparison_bids=comparison, zip_code=zip_code, run_llm_pass=run_llm_pass)
    if run_llm_pass:
        record_bid_evaluation_usage(
            evaluating_user_id, model="bid_evaluator", project_id=bid_row["project_id"],
        )

    return {
        "completeness_score": report.completeness.score,
        "missing_clauses": list(report.completeness.missing),
        "red_flags": [{"key": f.key, "severity": f.severity, "message": f.message} for f in report.red_flags],
        "price_assessments": [
            {"description": a.description, "signal": a.signal, "detail": a.detail}
            for a in report.price_assessments
        ],
        "llm_flags": list(report.llm_flags),
        "disclaimer": report.disclaimer,
    }


def _bid_to_response(bid_row: dict, *, evaluating_user_id: UUID | None = None) -> dict:
    payload = dict(bid_row)
    payload["line_items"] = [dict(li) for li in db_client.list_bid_line_items(bid_row["id"])]
    profile = db_client.get_contractor_profile(bid_row["contractor_profile_id"])
    payload["contractor_business_name"] = (profile or {}).get("business_name")
    payload["evaluation"] = _evaluate(bid_row, evaluating_user_id=evaluating_user_id) if evaluating_user_id else None
    return payload


@router.post("/projects/{project_id}/bids", response_model=BidResponse, status_code=201)
def submit_bid(project_id: UUID, body: CreateBidRequest, current_user: CurrentUser, contractor: BiddableContractor) -> dict:
    """Submit a structured bid on an open project."""
    project = db_client.get_project(project_id)
    if not project or project.get("marketplace_status") != "open":
        raise HTTPException(status_code=422, detail="This project isn't open for bidding.")

    license_row = db_client.get_contractor_license(body.license_id)
    if not license_row or license_row["contractor_profile_id"] != contractor["id"]:
        raise HTTPException(status_code=404, detail="License not found.")

    try:
        bid = bids_service.create_bid(
            project_id=project_id,
            contractor_profile_id=contractor["id"],
            license_id=body.license_id,
            line_items=[item.model_dump() for item in body.line_items],
            allowances=body.allowances,
            exclusions=body.exclusions,
            payment_schedule=body.payment_schedule,
            permit_responsibility=body.permit_responsibility,
            timeline_start=body.timeline_start,
            timeline_end=body.timeline_end,
            timeline_notes=body.timeline_notes,
            warranty_text=body.warranty_text,
            warranty_years=body.warranty_years,
            change_order_terms=body.change_order_terms,
            lien_waiver_included=body.lien_waiver_included,
            materials_source=body.materials_source,
            materials_source_connector=body.materials_source_connector,
            materials_source_notes=body.materials_source_notes,
            notes=body.notes,
        )
    except Exception as exc:
        if "uq_bids_one_active_per_contractor_project" in str(exc):
            raise HTTPException(
                status_code=409,
                detail="You already have an active bid on this project. Withdraw it before resubmitting.",
            ) from exc
        raise
    return _bid_to_response(bid, evaluating_user_id=current_user["user_id"])


@router.get("/projects/{project_id}/bids", response_model=list[BidResponse])
def list_project_bids(project_id: UUID, current_user: CurrentUser) -> list[dict]:
    """All bids on a project — homeowner/staff only, so competitors never see
    each other's bids. Inline role check, mirroring commerce.py's precedent
    rather than importing projects.py's private _require_role."""
    role = db_client.get_project_role(project_id, current_user["user_id"])
    if not role:
        raise HTTPException(status_code=403, detail="Insufficient project privileges.")
    rows = db_client.list_bids_for_project(project_id)
    return [_bid_to_response(row, evaluating_user_id=current_user["user_id"]) for row in rows]


@router.get("/bids/mine", response_model=list[BidResponse])
def list_my_bids(contractor: Contractor) -> list[dict]:
    """The caller's own bid history. No evaluation attached — that's a
    homeowner-facing comparison tool, not needed for a contractor's own list."""
    rows = db_client.list_bids_for_contractor(contractor["id"])
    return [_bid_to_response(row) for row in rows]


@router.get("/bids/{bid_id}", response_model=BidResponse)
def get_bid(bid_id: UUID, current_user: CurrentUser) -> dict:
    """Fetch one bid — the owning contractor, or the project's homeowner/staff."""
    bid = db_client.get_bid(bid_id)
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found.")
    profile = db_client.get_contractor_profile_by_user(current_user["user_id"])
    is_owning_contractor = bool(profile) and profile["id"] == bid["contractor_profile_id"]
    has_project_role = bool(db_client.get_project_role(bid["project_id"], current_user["user_id"]))
    if not is_owning_contractor and not has_project_role:
        raise HTTPException(status_code=403, detail="Not authorized to view this bid.")
    return _bid_to_response(bid, evaluating_user_id=current_user["user_id"])


@router.post("/bids/{bid_id}/withdraw", response_model=BidResponse)
def withdraw_bid(bid_id: UUID, contractor: Contractor) -> dict:
    """Withdraw the caller's own submitted bid."""
    bid = db_client.get_bid(bid_id)
    if not bid or bid["contractor_profile_id"] != contractor["id"]:
        raise HTTPException(status_code=404, detail="Bid not found.")
    updated = db_client.withdraw_bid(bid_id)
    if not updated:
        raise HTTPException(status_code=409, detail="Bid is not in a withdrawable state.")
    return _bid_to_response(updated)


@router.post("/projects/{project_id}/bids/{bid_id}/award", response_model=BidResponse)
def award_bid(project_id: UUID, bid_id: UUID, current_user: CurrentUser) -> dict:
    """Award a bid (project owner only): the winner -> awarded, every other
    submitted bid on the project -> declined."""
    role = db_client.get_project_role(project_id, current_user["user_id"])
    if role != "owner":
        raise HTTPException(status_code=403, detail="Insufficient project privileges.")
    bid = db_client.get_bid(bid_id)
    if not bid or bid["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Bid not found.")
    if bid["status"] != "submitted":
        raise HTTPException(status_code=422, detail="Only a submitted bid can be awarded.")
    updated = db_client.award_bid(project_id, bid_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Bid not found.")
    return _bid_to_response(updated)
