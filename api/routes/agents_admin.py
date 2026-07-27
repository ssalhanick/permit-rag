"""
api/routes/agents_admin.py — superadmin agent dashboard
=======================================================
Phase 3's first demo-able surface (v1): the action queue and the metadata review
pane. The Corpus Metadata Validator (agent #13) produces proposals and nothing
can act on them without a review UI, so the queue ships with the validator.

**Dashboard v2 (Phase 5)** adds the read/measure + control surfaces over the
trace store the Phase-0 telemetry fills: ``/scorecard`` (per-agent rollup),
``/autonomy`` (list + set, clamped to ceiling), ``/runs/{id}/trace`` (the
explorer), ``/feedback-summary`` (the answer feedback loop + correction rate),
and ``/corrections`` + ``/corrections/{id}/confirm`` — the queue where a human
confirms a Performance Review (#24) attribution, turning it into training data.

v1 surfaces:

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
from datetime import UTC, date, datetime, timedelta
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


@router.get("/documents")
def list_corpus_documents(
    _user: Annotated[dict, Depends(require_superadmin)],
    status: str | None = Query(None),
    municipality: str | None = Query(None),
) -> dict[str, Any]:
    """
    Read-only corpus metadata view for superadmins.

    Returns every document's stored metadata (all statuses, including ``draft``),
    so the corpus's gaps — null ``effective_date``, missing ``checksum_sha256`` —
    are visible on the site. Review and edit stay in the metadata-review pane;
    this is a look-only surface.
    """
    docs = db_client.list_documents(status=status, municipality=municipality)
    return {"documents": docs, "count": len(docs)}


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


# ── Agent Glossary ───────────────────────────────────────────

GLOSSARY_DATA: list[dict[str, Any]] = [
    {
        "name": "manager",
        "display_name": "Pipeline Manager / Orchestrator",
        "category": "Control & Safety",
        "tier": "cheap",
        "execution_mode": "Hybrid (Deterministic State Machine + Delegation)",
        "autonomy_ceiling": "L3",
        "description": "Central orchestrator for the multi-wave /query/answer RAG pipeline. Coordinates intent routing, query deconstruction, retrieval, grounding checks, answer generation, and citation verification across 5 waves.",
        "dependencies": {
            "calls": [
                "permit_classifier", "jurisdiction_resolver", "project_context",
                "query_deconstructor", "retriever", "conflict_detector",
                "mini_rag_conflicts", "prompt_router", "budget_governor",
                "answer_generator", "citation_verifier", "media_curator", "guardrail"
            ],
            "called_by": ["api/routes/query.py (/query/answer)"]
        },
        "inputs": ["query", "top_k", "municipality", "address", "project_id", "chunk_ids"],
        "outputs": ["ManagerResult (ArtifactRefs, answer text, citations, conflict warnings, media links, abstain status)"],
        "metrics": ["routing_accuracy", "plan_length", "replan_rate", "react_iterations"],
        "governance_rules": ["Bounded at MAX_ITERATIONS = 6", "Must never import commerce/, forms/, or bids/ directly"]
    },
    {
        "name": "budget_governor",
        "display_name": "Budget & Token Governor",
        "category": "Control & Safety",
        "tier": "cheap",
        "execution_mode": "Deterministic",
        "autonomy_ceiling": "L3",
        "description": "Tracks token usage and dollar budgets across agent runs. Enforces tier degradation (e.g. Sonnet -> Haiku) and context trimming when token/cost caps are approached.",
        "dependencies": {
            "calls": [],
            "called_by": ["manager", "rag.agent_runtime"]
        },
        "inputs": ["agent_name", "context chunks", "budget_limits"],
        "outputs": ["Degraded chunk sets", "Tier overrides", "Token usage accounting"],
        "metrics": ["budget_trips", "degradation_rate"],
        "governance_rules": ["Deterministic execution", "Cannot be bypassed by non-superadmins"]
    },
    {
        "name": "prompt_router",
        "display_name": "Prompt Router & Persona Composer",
        "category": "Control & Safety",
        "tier": "cheap",
        "execution_mode": "Deterministic Fragment Lookup",
        "autonomy_ceiling": "L3",
        "description": "Assembles persona-tailored system prompts (DIY homeowner, contractor, architect, inspector, research) and jurisdiction-specific regulatory fragments dynamically.",
        "dependencies": {
            "calls": ["rag/prompts/ fragment library"],
            "called_by": ["manager"]
        },
        "inputs": ["persona", "jurisdiction", "intent", "experience", "project_notes"],
        "outputs": ["RoutedPrompt (composed system prompt string, max_tokens, persona, fragment_ids)"],
        "metrics": ["fragment_selection_accuracy", "persona_appropriateness", "default_to_research_rate"],
        "governance_rules": ["Defaults to 'research' persona when user persona is missing/unknown"]
    },
    {
        "name": "guardrail",
        "display_name": "Output & Truncation Guardrail",
        "category": "Control & Safety",
        "tier": "cheap",
        "execution_mode": "Deterministic Rules",
        "autonomy_ceiling": "L3",
        "description": "Monitors output generation for truncation, incomplete answers, and untrusted external media URLs. Filters out unverified domains.",
        "dependencies": {
            "calls": [],
            "called_by": ["manager"]
        },
        "inputs": ["GenerationResult", "query", "entity_id", "media_refs"],
        "outputs": ["Truncation status", "Sanitized media_refs list"],
        "metrics": ["guard_trip_rate"],
        "governance_rules": ["Non-fatal check; logs warnings without throwing 500 errors"]
    },
    {
        "name": "answer_generator",
        "display_name": "Compliance Answer Generator",
        "category": "Answer Synthesis",
        "tier": "mid",
        "execution_mode": "LLM-backed (Claude Sonnet / Haiku)",
        "autonomy_ceiling": "L3",
        "description": "Synthesizes formal municipal building compliance answers grounded exclusively in retrieved code chunks with required inline citations [doc_id, chunk_index].",
        "dependencies": {
            "calls": ["rag.agent_runtime"],
            "called_by": ["manager"]
        },
        "inputs": ["user query", "passing retrieved chunks", "RoutedPrompt", "project_context"],
        "outputs": ["GenerationResult (answer string, citations list, model, token usage, latency)"],
        "metrics": ["faithfulness", "answer_relevancy", "citation_density"],
        "governance_rules": ["Must include at least one valid inline citation", "Never cite superseded documents as sole source"]
    },
    {
        "name": "permit_classifier",
        "display_name": "Permit Type Classifier",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Deterministic NLI & Heuristics",
        "autonomy_ceiling": "L3",
        "description": "Classifies the required permit categories (building, electrical, plumbing, mechanical, zoning, fire, energy, demolition) relevant to the user query.",
        "dependencies": {
            "calls": [],
            "called_by": ["manager"]
        },
        "inputs": ["query text"],
        "outputs": ["List of permit category strings"],
        "metrics": ["permit_type_f1"],
        "governance_rules": ["Non-blocking; defaults to empty list [] on error"]
    },
    {
        "name": "jurisdiction_resolver",
        "display_name": "Jurisdiction & Geocoding Resolver",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Deterministic GIS & Geocoding",
        "autonomy_ceiling": "L3",
        "description": "Geocodes project addresses or parses location names to identify the governing municipality (Dallas, Fort Worth, Plano, Frisco, McKinney).",
        "dependencies": {
            "calls": ["GIS address geocoding"],
            "called_by": ["manager"]
        },
        "inputs": ["address string or site description"],
        "outputs": ["Municipality name string"],
        "metrics": ["municipality_accuracy"],
        "governance_rules": ["Precedence: explicit request > project kickoff > geocoded address"]
    },
    {
        "name": "conflict_detector",
        "display_name": "Municipal Code Conflict Detector",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Deterministic Rule Matching",
        "autonomy_ceiling": "L3",
        "description": "Detects conflicts or contradictory regulations between retrieved municipal ordinances and state/federal building standards.",
        "dependencies": {
            "calls": [],
            "called_by": ["manager"]
        },
        "inputs": ["list of retrieved chunks"],
        "outputs": ["list of ConflictWarning items"],
        "metrics": ["detection_precision", "false_alarm_rate"],
        "governance_rules": ["Must surface ConflictWarning rather than silently resolving code differences"]
    },
    {
        "name": "citation_verifier",
        "display_name": "Citation & Grounding Verifier",
        "category": "Control & Safety",
        "tier": "mid",
        "execution_mode": "Hybrid (Deterministic Span Match + LLM Entailment)",
        "autonomy_ceiling": "L3",
        "description": "Verifies that every statement and citation in the generated compliance answer is backed by source chunks. Flags hallucinated or unsupported citations.",
        "dependencies": {
            "calls": ["rag.agent_runtime"],
            "called_by": ["manager"]
        },
        "inputs": ["generated answer text", "citations list", "source chunks"],
        "outputs": ["Verification report", "unsupported_citations list", "claim precision/recall"],
        "metrics": ["claim_precision", "claim_recall"],
        "governance_rules": ["Runs in Wave 5 post-generation; flags hallucinated claims without blocking response delivery"]
    },
    {
        "name": "query_deconstructor",
        "display_name": "Compound Query Deconstructor",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Hybrid (Deterministic Gating + Single-shot LLM)",
        "autonomy_ceiling": "L3",
        "description": "Deconstructs complex multi-part building queries into individual sub-questions to allow targeted parallel retrievals across different code sections.",
        "dependencies": {
            "calls": ["rag.retriever"],
            "called_by": ["manager"]
        },
        "inputs": ["complex query text"],
        "outputs": ["sub_questions list"],
        "metrics": ["sub_question_coverage", "filter_precision"],
        "governance_rules": ["Gated deterministically: simple queries bypass LLM deconstruction"]
    },
    {
        "name": "permit_strategy",
        "display_name": "Permit Strategy & Fee Planner",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Hybrid (Deterministic Calculation + LLM Guidance Note)",
        "autonomy_ceiling": "L3",
        "description": "Plans required permit filing sequences, estimates filing fees, and outlines submittal prerequisites for construction projects.",
        "dependencies": {
            "calls": ["db/client.py"],
            "called_by": ["api/routes/projects.py", "manager"]
        },
        "inputs": ["project_id", "municipality", "permit_types"],
        "outputs": ["PermitPlan (permit list, submission order, fee estimates, strategy notes)"],
        "metrics": ["permit_set_f1"],
        "governance_rules": ["Calculations are deterministic; only the strategy note uses an LLM"]
    },
    {
        "name": "mini_rag_conflicts",
        "display_name": "Project Upload Conflict Detector",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Deterministic Comparison",
        "autonomy_ceiling": "L3",
        "description": "Compares user-uploaded project documents (architectural drawings, contractor specs) against city municipal code chunks to identify project discrepancies.",
        "dependencies": {
            "calls": [],
            "called_by": ["manager"]
        },
        "inputs": ["corpus chunks", "user project chunks"],
        "outputs": ["upload_conflicts list"],
        "metrics": ["detection_precision"],
        "governance_rules": ["Non-blocking check; flags project vs code differences as warnings"]
    },
    {
        "name": "project_context",
        "display_name": "Project Context & Fact Loader",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Deterministic DB Lookup",
        "autonomy_ceiling": "L3",
        "description": "Loads project facts, site location, kickoff specs, active room scans, and user preferences into the active pipeline session.",
        "dependencies": {
            "calls": ["db/client.py"],
            "called_by": ["manager"]
        },
        "inputs": ["project_id"],
        "outputs": ["project_context dict / ArtifactRef"],
        "metrics": ["fact_coverage"],
        "governance_rules": ["Runs in Wave 1; cached in ArtifactStore per session"]
    },
    {
        "name": "design_intent",
        "display_name": "Design Intent & Spec Parser",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "LLM Structured Extraction",
        "autonomy_ceiling": "L2",
        "description": "Parses unstructured architectural notes, room scan specs, and construction goals into a structured design intent schema for compliance checking.",
        "dependencies": {
            "calls": ["rag.agent_runtime"],
            "called_by": ["api/routes/projects.py"]
        },
        "inputs": ["room scan specs", "architectural notes"],
        "outputs": ["Structured design intent overlay"],
        "metrics": ["schema_validity", "overlay_precision"],
        "governance_rules": ["Validated against Pydantic schema before saving"]
    },
    {
        "name": "media_curator",
        "display_name": "Instructional Media & DIY Linker",
        "category": "Domain & Context",
        "tier": "cheap",
        "execution_mode": "Deterministic Mapping + Semantic Search",
        "autonomy_ceiling": "L3",
        "description": "Curates verified step-by-step instructional video tutorials, official guides, and timestamped media links for DIY homeowner queries.",
        "dependencies": {
            "calls": ["db/client.py"],
            "called_by": ["manager"]
        },
        "inputs": ["query", "persona ('diy')", "jurisdiction", "permit_types"],
        "outputs": ["media_refs list (title, URL, channel, timestamp)"],
        "metrics": ["link_liveness", "relevance", "zero_unsourced_urls"],
        "governance_rules": ["Runs on DIY persona paths; all URLs checked against guardrail allowlists"]
    },
    {
        "name": "metadata_validator",
        "display_name": "Corpus Metadata Validator",
        "category": "Governance & Maintenance",
        "tier": "mid",
        "execution_mode": "Hybrid (Deterministic Schema Check + LLM Sampling)",
        "autonomy_ceiling": "L1",
        "description": "Audits corpus document metadata (effective_date, doc_type, authority_level, subject_tags) against chunk text. Generates proposals for human review in the dashboard queue.",
        "dependencies": {
            "calls": ["rag.agent_runtime", "ingestion.governance"],
            "called_by": ["ingestion scripts", "admin action queue"]
        },
        "inputs": ["Corpus document rows", "sampled chunks"],
        "outputs": ["ValidationReport", "action_items proposals"],
        "metrics": ["enum_precision", "date_extraction_accuracy", "tag_vocab_compliance"],
        "governance_rules": ["L1 Autonomy (Human-in-the-loop): Cannot edit corpus directly. Writes proposals to action queue; human approval in Metadata Review Pane invokes ingestion.governance."]
    }
]


@router.get("/glossary")
def get_agent_glossary(
    _user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """Complete glossary of agents, how they are used, dependencies, and rules."""
    return {"agents": GLOSSARY_DATA, "count": len(GLOSSARY_DATA)}


@router.get("/scorecard")
def agent_scorecard(
    _user: Annotated[dict, Depends(require_superadmin)],
    days: int = Query(7, ge=1, le=365),
) -> dict[str, Any]:
    """Per-agent rollup (calls, cost, latency, deterministic rate, error rate)."""
    since = datetime.now(UTC) - timedelta(days=days)
    return {"days": days, "agents": db_client.agent_scorecard(since=since)}


class SetAutonomyRequest(BaseModel):
    """Set an agent's autonomy level (clamped to its ceiling in SQL)."""

    level: str = Field(pattern="^L[0-3]$")
    scope: str = "default"


class ConfirmCorrectionRequest(BaseModel):
    """Confirm a Performance Review attribution, optionally re-assigning blame."""

    attributed_agent: str | None = None


@router.get("/autonomy")
def list_autonomy(
    _user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """Every agent's autonomy row (current level + ceiling) for the control panel."""
    return {"agents": db_client.list_agent_autonomy()}


@router.post("/autonomy/{agent_name}")
def set_autonomy(
    agent_name: str,
    body: SetAutonomyRequest,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """Set an agent's autonomy level. 409 when the level exceeds its ceiling."""
    row = db_client.set_agent_autonomy(
        agent_name, body.scope, current_level=body.level, updated_by=user["user_id"]
    )
    if row is None:
        raise HTTPException(
            status_code=409,
            detail=f"{body.level} exceeds {agent_name}'s ceiling (or it is unregistered).",
        )
    return {"agent": row}


@router.get("/runs/{run_id}/trace")
def get_run_trace(
    run_id: UUID,
    _user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """A run's full trace — the row plus its ordered steps — for the explorer."""
    run = db_client.get_agent_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"run": run, "steps": db_client.list_agent_steps(run_id)}


@router.get("/feedback-summary")
def feedback_summary(
    _user: Annotated[dict, Depends(require_superadmin)],
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Answer-feedback totals + per-agent correction rate for the window."""
    since = datetime.now(UTC) - timedelta(days=days)
    return {
        "days": days,
        "feedback": db_client.answer_feedback_counts(since=since),
        "corrections_by_agent": db_client.correction_rate_by_agent(since=since),
    }


@router.get("/corrections")
def list_corrections(
    _user: Annotated[dict, Depends(require_superadmin)],
    confirmed: bool | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> dict[str, Any]:
    """Corrections queue; ``confirmed=false`` is the Performance Review triage list."""
    items = db_client.list_agent_corrections(confirmed=confirmed, limit=limit)
    return {"corrections": items, "count": len(items)}


@router.post("/corrections/{correction_id}/confirm")
def confirm_correction(
    correction_id: UUID,
    body: ConfirmCorrectionRequest,
    user: Annotated[dict, Depends(require_superadmin)],
) -> dict[str, Any]:
    """Confirm a Performance Review attribution — the human sign-off (training data)."""
    row = db_client.confirm_agent_correction(
        correction_id,
        attributed_agent=body.attributed_agent,
        confirmed_by=user["user_id"],
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Correction not found.")
    return {"correction": row}


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
