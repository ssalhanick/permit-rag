"""
api/design_intent_helpers.py — Shared design-intent route logic.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from api.schemas import DesignIntentRequest, DesignIntentUsage
from db import client as db_client


def _month_start() -> datetime:
    """Return UTC midnight on the first day of the current month."""
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _check_token_cap(user_id: UUID) -> None:
    """Raise HTTP 429 when the user exceeds the monthly design-intent token cap."""
    cap = int(os.environ.get("DESIGN_INTENT_MONTHLY_TOKEN_CAP", "500000"))
    if cap <= 0:
        return
    used = db_client.sum_design_intent_tokens(user_id, since=_month_start())
    if used >= cap:
        raise HTTPException(
            status_code=429,
            detail=f"Design preview token cap reached ({used}/{cap} this month).",
        )


def _resolve_room_scan_row(rows: list[dict[str, Any]], scan_id: UUID) -> dict[str, Any]:
    """Find a room scan row by id or raise 404."""
    row = next((r for r in rows if r["id"] == scan_id), None)
    if not row or row.get("scan_type") != "room":
        raise HTTPException(status_code=404, detail="Room scan not found.")
    return row


def _usage_from_result(result: dict[str, Any]) -> DesignIntentUsage:
    """Build usage schema from parse_design_intent result."""
    usage = result.get("usage") or {}
    return DesignIntentUsage(
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        model=str(usage.get("model", "unknown")),
    )


def run_design_intent(
    *,
    user_id: UUID,
    project_id: UUID | None,
    scan_id: UUID,
    room_row: dict[str, Any],
    body: DesignIntentRequest,
) -> dict[str, Any]:
    """
    Parse design intent, enrich overlays, log token usage, return API payload.
    """
    from commerce.product_resolver import resolve_products_for_overlays
    from commerce.takeoff import extract_zip_from_address
    from rag.design_intent import parse_design_intent

    _check_token_cap(user_id)

    result = parse_design_intent(
        body.utterance,
        room_label=body.room_label or room_row.get("room_label"),
        room_derived=body.room_derived or room_row.get("derived"),
        surface_hints=body.surface_hints,
        selected_surface_id=body.selected_surface_id,
    )
    usage = _usage_from_result(result)

    zip_code = "75034"
    if project_id:
        project = db_client.get_project(project_id)
        zip_code = extract_zip_from_address((project or {}).get("address")) or zip_code

    enriched, candidates = resolve_products_for_overlays(
        result.get("overlays", []),
        room_derived=body.room_derived or room_row.get("derived"),
        zip_code=zip_code,
        utterance=body.utterance,
    )

    db_client.insert_design_intent_usage(
        user_id=user_id,
        project_id=project_id,
        room_scan_id=scan_id,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        model=usage.model,
    )

    return {
        "overlays": enriched,
        "explanation": result.get("explanation", ""),
        "product_candidates": candidates,
        "usage": usage.model_dump(),
    }
