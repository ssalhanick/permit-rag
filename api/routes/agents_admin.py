"""
api/routes/agents_admin.py — superadmin agent dashboard (v1)
=============================================================
Phase 3's first demo-able surface: the action queue and the metadata review
pane. The Corpus Metadata Validator (agent #13) produces proposals and nothing
can act on them without a review UI, so the queue ships with the validator.

Two slices this phase (the scorecard, trace explorer, autonomy, and prompts tabs
are Phase 5's dashboard v2):

* **Action queue** — every open ``agent_action_items`` row, most severe first;
  resolve or dismiss inline with a note.
* **Metadata review** — the validator's ``needs_review`` items, each carrying
  its proposals and source-chunk citations; approving one writes the correction
  through ``ingestion.governance`` (the only corpus writer) and closes the loop
  with an ``agent_corrections`` row.

Auth: every route is superadmin-only. The backend gate reuses ``is_superadmin``
(``api/auth.py``); the frontend route guard is the new part (Phase 3, frontend).
Non-superadmins get 403, matching the acceptance criterion.

Import boundary: api/ → rag/, commerce/, db/, audit/, ingestion/, stdlib.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import get_optional_current_user, is_superadmin
from db import client as db_client
from ingestion import governance

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/agents", tags=["admin", "agents"])

_METADATA_AGENT = "metadata_validator"
_METADATA_KINDS = ("metadata_needs_review", "metadata_invalid")


# ── Auth dependency ──────────────────────────────────────────


def require_superadmin(
    current_user: Annotated[dict | None, Depends(get_optional_current_user)] = None,
) -> dict:
    """FastAPI dependency: 403 unless the caller is a global superadmin."""
    if not is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Superadmin role required.")
    return current_user  # type: ignore[return-value]


# ── Request models ───────────────────────────────────────────


class ResolveActionItemRequest(BaseModel):
    """Resolve or dismiss an action item, with an optional note."""

    status: str = Field(pattern="^(resolved|dismissed|acknowledged)$")
    note: str | None = None


class MetadataApplyRequest(BaseModel):
    """Approve a validator proposal: which corrected fields to write."""

    item_id: UUID
    effective_date: date | None = None
    doc_type: str | None = None
    authority_level: str | None = None
    subject_tags: list[str] | None = None
    note: str | None = None


# ── Action queue ─────────────────────────────────────────────


@router.get("/action-items")
def list_action_items(
    _user: Annotated[dict, Depends(require_superadmin)],
    status: str = Query("open"),
    source_agent: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    """List action items for the queue, most severe first."""
    items = db_client.list_action_items(
        status=status, source_agent=source_agent, limit=limit
    )
    return {"items": items, "count": len(items)}


@router.post("/action-items/{item_id}/resolve")
def resolve_action_item(
    item_id: UUID,
    body: ResolveActionItemRequest,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """
    Resolve, acknowledge, or dismiss an action item.

    Resolving or dismissing closes the loop with an ``agent_corrections`` row so
    triage becomes training data (docs/agent_architecture.md, "Resolution closes
    the loop"). Acknowledging does not — it is not yet an outcome.
    """
    updated = db_client.resolve_action_item(
        item_id,
        status=body.status,
        resolved_by=user["user_id"],
        resolution_note=body.note,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Action item not found.")

    if body.status in ("resolved", "dismissed"):
        _record_correction(updated, source="step", confirmed=body.status == "resolved",
                           notes=body.note, created_by=user["user_id"])
    return {"item": updated}


# ── Metadata review ──────────────────────────────────────────


@router.get("/metadata-review")
def list_metadata_review(
    _user: Annotated[dict, Depends(require_superadmin)],
    status: str = Query("open"),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    """
    List the validator's metadata items, each with its proposals + citations.

    The proposals and their source-chunk citations ride in each item's
    ``evidence`` JSONB (written by the validator), so the pane needs no join.
    """
    items = db_client.list_action_items(
        status=status, source_agent=_METADATA_AGENT, limit=limit
    )
    return {"items": items, "count": len(items)}


@router.post("/metadata-review/{doc_id}/apply")
def apply_metadata_correction(
    doc_id: str,
    body: MetadataApplyRequest,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """
    Approve a validator proposal and write the correction (the L1 approve flow).

    The write goes through ``ingestion.governance.apply_metadata_correction`` —
    the single corpus writer — never inline here. The originating action item is
    then resolved and an ``agent_corrections`` row records the human-confirmed
    fix as artifact-level training data.
    """
    if not any((body.effective_date, body.doc_type, body.authority_level,
                body.subject_tags)):
        raise HTTPException(status_code=400, detail="No corrected fields supplied.")

    try:
        updated_doc = governance.apply_metadata_correction(
            doc_id,
            effective_date=body.effective_date,
            doc_type=body.doc_type,
            authority_level=body.authority_level,
            subject_tags=body.subject_tags,
            actor=str(user["user_id"]),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    item = db_client.resolve_action_item(
        body.item_id,
        status="resolved",
        resolved_by=user["user_id"],
        resolution_note=body.note or f"Applied metadata correction to {doc_id}.",
    )
    if item is not None:
        _record_correction(
            item, source="artifact", confirmed=True, created_by=user["user_id"],
            notes=body.note,
            actual=_applied_summary(body),
        )
    return {"document": updated_doc, "item": item}


# ── Helpers ──────────────────────────────────────────────────


def _record_correction(
    item: dict[str, Any],
    *,
    source: str,
    confirmed: bool,
    created_by: UUID,
    notes: str | None = None,
    actual: str | None = None,
) -> None:
    """Write an agent_corrections row; a trace blip must not fail the request."""
    try:
        db_client.insert_agent_correction(
            source=source,
            run_id=item.get("run_id"),
            attributed_agent=item.get("source_agent"),
            severity=item.get("severity"),
            entity_type=item.get("entity_type") or None,
            entity_id=item.get("entity_id") or None,
            expected=item.get("proposed_action"),
            actual=actual,
            notes=notes,
            confirmed=confirmed,
            created_by=created_by,
        )
    except Exception as exc:  # correction logging is not business logic
        log.warning("Could not record correction for item %s: %s", item.get("id"), exc)


def _applied_summary(body: MetadataApplyRequest) -> str:
    """One-line record of what was written, for the correction row."""
    parts = []
    if body.effective_date:
        parts.append(f"effective_date={body.effective_date.isoformat()}")
    if body.doc_type:
        parts.append(f"doc_type={body.doc_type}")
    if body.authority_level:
        parts.append(f"authority_level={body.authority_level}")
    if body.subject_tags is not None:
        parts.append(f"subject_tags={body.subject_tags}")
    return "; ".join(parts)
