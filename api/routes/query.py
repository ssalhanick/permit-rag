"""
api/routes/query.py — POST /query and POST /query/answer endpoints
====================================================================
/query: retrieval only — returns ranked chunks with metadata.
/query/answer: retrieval + generation — returns a cited answer from Claude.

**Phase 2.** The hand-wired chain that used to live inside ``query_answer`` —
classify, resolve jurisdiction, retrieve, guard, detect conflicts, load project
context, generate — now lives in ``rag/agents/manager.py``. This module keeps
only what is genuinely HTTP's: request identity, the LangSmith root span, the
mapping from a plan failure to a status code, and response assembly. The port is
behaviour-preserving by construction; ``tests/test_query_answer_route.py``
asserts it without a single edit to its expectations.

Retrieval and the grounding thresholds are passed *into* the Manager rather than
imported by it. ``rag/agents/`` may not depend on ``api/``, and these knobs are
configured here — so the route, which is allowed to see both sides, injects them.

Import boundary: api/ → rag/, commerce/, db/, audit/, standard library (AGENTS.md).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from api.auth import get_current_user
from api.schemas import (
    AHJDisclaimer,
    AnswerResponse,
    ChunkResponse,
    CitationResponse,
    ConflictWarning,
    DiagnosticsResponse,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from audit.logger import annotate_run, traced_run
from db.client import get_jurisdiction
from rag.agents.manager import ManagerDeps, ManagerError, ManagerRequest, run_query_plan
from rag.generator import PROMPT_VERSION
from rag.retriever import retrieve, retrieve_with_project

log = logging.getLogger(__name__)

router = APIRouter(tags=["query"])
MIN_GROUNDED_CHUNKS = int(os.environ.get("RAG_GUARD_MIN_CHUNKS", "3"))
MIN_GROUNDED_TOP_SIM = float(os.environ.get("RAG_GUARD_MIN_TOP_SIM", "0.74"))

_AHJ_DISCLAIMER_TEXT = (
    "Results are based on published ordinance text and may not reflect current "
    "interpretive policy, variance precedents, or informal guidance from the "
    "Authority Having Jurisdiction (AHJ). The AHJ — your city's building department "
    "— has final authority over all permit decisions. Always verify requirements "
    "with the relevant department before proceeding. This tool is a research aid, "
    "not a substitute for professional review."
)

# Clarification nudge (Phase 4): shown when no persona was set and the answer used
# the neutral `research` default. Set on the response for the frontend to surface.
_PERSONA_NUDGE_TEXT = (
    "No role set — answered neutrally. Set your role (DIY, hiring a contractor, "
    "contractor, or research) for tailored answers."
)


def _nudge_for(plan: Any) -> str | None:
    """The persona nudge text when the plan defaulted persona, else None."""
    return _PERSONA_NUDGE_TEXT if plan.persona_defaulted else None


def _build_ahj_disclaimer(municipality: str | None) -> AHJDisclaimer:
    """
    Return the AHJ disclaimer, pulling the dept portal URL from the jurisdictions
    table. Falls back gracefully if the municipality is unknown or DB is unreachable.
    """
    learn_more_url: str | None = None
    if municipality:
        try:
            row = get_jurisdiction(municipality.lower())
            if row:
                learn_more_url = row.get("dept_url")
        except Exception:
            pass  # non-fatal — disclaimer text still shown without link
    return AHJDisclaimer(text=_AHJ_DISCLAIMER_TEXT, learn_more_url=learn_more_url)


def _langsmith_enabled() -> bool:
    """Return true when LangSmith tracing is configured and installed."""
    if os.environ.get("LANGCHAIN_TRACING_V2", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    if not os.environ.get("LANGSMITH_API_KEY", "").strip():
        return False
    try:
        import langsmith.run_trees  # noqa: F401
    except ImportError:
        log.warning("LangSmith SDK not installed; API tracing disabled.")
        return False
    return True


def _start_trace(
    name: str,
    run_type: str,
    inputs: dict[str, Any],
    parent: Any = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    """Start a LangSmith run/span safely and return its handle."""
    try:
        if parent is None:
            from langsmith.run_trees import RunTree

            run = RunTree(
                name=name,
                run_type=run_type,
                inputs=inputs,
                project_name=os.environ.get("LANGCHAIN_PROJECT", "permit-rag-app"),
                extra=extra,
            )
        else:
            run = parent.create_child(name=name, run_type=run_type, inputs=inputs, extra=extra)
        run.post()
        return run
    except Exception as exc:
        log.warning("LangSmith trace start failed (%s): %s", name, exc)
        return None


def _end_trace(run: Any, outputs: dict[str, Any] | None = None, error: str | None = None) -> None:
    """Finalize LangSmith run/span safely."""
    if run is None:
        return
    try:
        run.end(outputs=outputs, error=error)
        patched = run.patch()
        if hasattr(patched, "result"):
            patched.result()
    except Exception as exc:
        log.warning("LangSmith trace end failed: %s", exc)


class _LangSmithObserver:
    """
    Bridge the Manager's step callbacks onto this route's LangSmith spans.

    The Manager cannot open spans itself — that would put a LangSmith dependency
    inside ``rag/agents/``. It announces stage boundaries instead, and this
    adapter reproduces the exact ``api_retrieval`` / ``api_generation`` children
    the route emitted before Phase 2.
    """

    _SPANS: ClassVar[dict[str, tuple[str, str]]] = {
        "retrieval": ("api_retrieval", "tool"),
        "generation": ("api_generation", "llm"),
    }

    def __init__(self, root: Any, *, session_id: str, request_id: str) -> None:
        """Create spans beneath ``root``, tagging generation with request identity."""
        self._root = root
        self._session_id = session_id
        self._request_id = request_id
        self._open: dict[str, Any] = {}

    def started(self, stage: str, inputs: dict[str, Any]) -> None:
        """Open the child span for a stage."""
        name, run_type = self._SPANS[stage]
        extra = None
        if stage == "generation":
            inputs = {**inputs, "session_id": self._session_id, "request_id": self._request_id}
            extra = {"metadata": {"prompt_version": PROMPT_VERSION}}
        self._open[stage] = _start_trace(
            name=name, run_type=run_type, inputs=inputs, parent=self._root, extra=extra
        )

    def finished(self, stage: str, outputs: dict[str, Any]) -> None:
        """Close a stage's span with its outputs."""
        _end_trace(self._open.pop(stage, None), outputs=outputs)

    def failed(self, stage: str, error: str) -> None:
        """Close a stage's span with an error."""
        _end_trace(self._open.pop(stage, None), error=error)


def _root_trace_error(exc: ManagerError) -> str:
    """
    The string the root span records for a plan failure.

    An empty corpus reports the short form on the trace and the long form to the
    caller — preserved verbatim from the pre-Phase-2 route.
    """
    return "No relevant chunks found." if exc.kind == "empty" else str(exc)


def _http_error(exc: ManagerError) -> HTTPException:
    """Map a plan failure onto the status code the route has always returned."""
    status = 422 if exc.stage == "grounding" else 500
    return HTTPException(status_code=status, detail=str(exc))


def _build_manager_deps(observer: Any) -> ManagerDeps:
    """
    Assemble the Manager's injected collaborators.

    ``retrieve_with_project`` and the two grounding thresholds are read from this
    module at call time, so an operator's env override — and a test's patch —
    both still apply.
    """
    return ManagerDeps(
        retrieve=retrieve_with_project,
        min_chunks=MIN_GROUNDED_CHUNKS,
        min_top_sim=MIN_GROUNDED_TOP_SIM,
        observer=observer,
    )


def _chunk_responses(chunks: list[dict[str, Any]]) -> list[ChunkResponse]:
    """Map retrieval chunk rows to the response model (shared by both paths)."""
    return [
        ChunkResponse(
            id=chunk["id"],
            document_id=chunk["document_id"],
            doc_id=chunk["doc_id"],
            chunk_index=chunk["chunk_index"],
            content=chunk["content"],
            municipality=chunk["municipality"],
            authority_level=chunk["authority_level"],
            doc_type=chunk["doc_type"],
            document_status=chunk["document_status"],
            source_tier=chunk.get("source_tier", 1),
            similarity=chunk.get("raw_similarity") or chunk["similarity"],
            raw_similarity=chunk.get("raw_similarity", chunk["similarity"]),
            reranked_score=chunk.get("reranked_score", chunk["similarity"]),
            provenance_weight=chunk.get("provenance_weight", 1.0),
            filtered_out=chunk.get("filtered_out", False),
        )
        for chunk in chunks
    ]


def _build_abstain_response(
    body: QueryRequest,
    plan: Any,
    root_trace: Any,
    background_tasks: BackgroundTasks,
    current_user: Any,
    started_at: float,
) -> AnswerResponse:
    """
    Build the 200 response for a grounding-floor abstain (Phase 4 query-UX).

    The abstain is a normal outcome: `answer` carries the conversational message,
    citations are empty, `chunks` still shows what retrieval found, and the nudge
    + disclaimer ride along. Logged to history (model="abstained") so the abstain
    rate is visible, and the root span closes with outputs, not an error.
    """
    result = plan.retrieval
    all_chunks = _chunk_responses(result.chunks)
    diagnostics = DiagnosticsResponse(
        top_similarity=result.top_similarity,
        mean_similarity=result.mean_similarity,
        unique_doc_count=len(result.unique_documents),
        unique_doc_ids=result.unique_documents,
    )
    response = AnswerResponse(
        query=body.query,
        answer=plan.abstain_message or "",
        citations=[],
        model="abstained",
        input_tokens=0,
        output_tokens=0,
        latency_generation_ms=0,
        latency_retrieval_ms=result.latency_ms,
        num_chunks=0,
        total_chunks_retrieved=len(all_chunks),
        chunks=all_chunks,
        diagnostics=diagnostics,
        permit_types=plan.permit_types,
        ahj_disclaimer=_build_ahj_disclaimer(plan.effective_municipality),
        resolved_municipality=plan.resolved_municipality,
        conflict_warnings=[],
        persona_nudge=_nudge_for(plan),
        abstained=True,
    )
    try:
        from db import client as db_client
        background_tasks.add_task(
            db_client.insert_query_log,
            query_text=body.query,
            model="abstained",
            municipality=body.municipality,
            top_k=body.top_k,
            chunk_ids=[c.id for c in all_chunks],
            answer_text=plan.abstain_message or "",
            citations=[],
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            user_id=current_user["user_id"] if (current_user and isinstance(current_user, dict)) else None,
            project_id=UUID(body.project_id) if body.project_id else None,
        )
    except Exception as exc:
        log.warning("could not schedule abstain query logging task: %s", exc)

    _end_trace(
        root_trace,
        outputs={
            "abstained": True,
            "num_chunks_retrieved": result.num_results,
            "top_similarity": result.top_similarity,
            "latency_retrieval_ms": result.latency_ms,
        },
    )
    return response


@router.post(
    "/query",
    response_model=QueryResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Retrieval failure"},
    },
    summary="Retrieve relevant document chunks",
    description=(
        "Embeds the query with nomic-embed-text-v1.5, performs dense "
        "cosine search via pgvector, and returns ranked chunks with "
        "metadata and quality diagnostics."
    ),
)
def query_chunks(
    body: QueryRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> QueryResponse:
    """Retrieve ranked chunks for a natural-language query."""
    try:
        result = retrieve(
            body.query,
            top_k=body.top_k,
            municipality=body.municipality,
            min_similarity=body.min_similarity,
        )
    except Exception as exc:
        log.exception("Retrieval failed for query: %s", body.query)
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval error: {exc}",
        ) from exc

    chunks = [
        ChunkResponse(
            id=chunk["id"],
            document_id=chunk["document_id"],
            doc_id=chunk["doc_id"],
            chunk_index=chunk["chunk_index"],
            content=chunk["content"],
            municipality=chunk["municipality"],
            authority_level=chunk["authority_level"],
            doc_type=chunk["doc_type"],
            document_status=chunk["document_status"],
            source_tier=chunk.get("source_tier", 1),
            similarity=chunk.get("raw_similarity") or chunk["similarity"],
            raw_similarity=chunk.get("raw_similarity", chunk["similarity"]),
            reranked_score=chunk.get("reranked_score", chunk["similarity"]),
            provenance_weight=chunk.get("provenance_weight", 1.0),
            filtered_out=chunk.get("filtered_out", False),
        )
        for chunk in result.chunks
    ]

    diagnostics = DiagnosticsResponse(
        top_similarity=result.top_similarity,
        mean_similarity=result.mean_similarity,
        unique_doc_count=len(result.unique_documents),
        unique_doc_ids=result.unique_documents,
    )

    return QueryResponse(
        query=result.query,
        top_k=result.top_k,
        municipality=result.municipality,
        num_results=result.num_results,
        latency_ms=result.latency_ms,
        model=result.model,
        chunks=chunks,
        diagnostics=diagnostics,
    )


@router.post(
    "/query/answer",
    response_model=AnswerResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Validation or low-confidence retrieval"},
        500: {"model": ErrorResponse, "description": "Retrieval or generation failure"},
    },
    summary="Generate a cited answer from retrieved chunks",
    description=(
        "Retrieves relevant chunks via dense search, then generates a "
        "cited answer using Claude. Returns the answer text with inline "
        "[doc_id, chunk N] citations, structured citation metadata, and "
        "the source chunks used as context."
    ),
)
@traced_run("query_answer")
def query_answer(
    body: QueryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> AnswerResponse:
    """Retrieve chunks and generate a cited answer via Claude."""
    started_at = time.perf_counter()
    session_id = request.headers.get("X-Client-Session-Id", "").strip() or "unknown"
    request_id = request.headers.get("X-Client-Request-Id", "").strip() or f"api-{int(time.time() * 1000)}"
    tracing_on = _langsmith_enabled()

    if not body.project_id and current_user and isinstance(current_user, dict):
        from db import client as db_client

        user_row = db_client.get_user_by_id(current_user["user_id"])
        if user_row and user_row.get("active_project_id"):
            body.project_id = str(user_row["active_project_id"])

    # Attach request identity to the trace run opened by @traced_run. Done
    # here rather than at the decorator because the active project is only
    # resolved above.
    annotate_run(
        user_id=current_user["user_id"] if isinstance(current_user, dict) else None,
        project_id=body.project_id,
        session_id=session_id,
    )

    metadata = {"prompt_version": PROMPT_VERSION}
    if current_user and isinstance(current_user, dict):
        metadata["user_id"] = str(current_user["user_id"])
        metadata["user_role"] = current_user["role"]
        if "username" in current_user:
            metadata["username"] = current_user["username"]
    if body.project_id:
        metadata["project_id"] = body.project_id

    root_trace = _start_trace(
        name="api_query_answer",
        run_type="chain",
        inputs={
            "session_id": session_id,
            "request_id": request_id,
            "query": body.query,
            "municipality": body.municipality,
            "top_k": body.top_k,
            "min_similarity": body.min_similarity,
        },
        extra={"metadata": metadata} if metadata else None,
    ) if tracing_on else None

    # 1-2. Delegate the whole chain to the Manager (Phase 2). Ordering, logging,
    # non-blocking failure handling, and the grounding guard all live there now.
    observer = _LangSmithObserver(
        root_trace, session_id=session_id, request_id=request_id
    ) if tracing_on else None
    try:
        plan = run_query_plan(
            ManagerRequest(
                query=body.query,
                top_k=body.top_k,
                municipality=body.municipality,
                address=body.address,
                min_similarity=body.min_similarity,
                project_id=body.project_id,
                chunk_ids=body.chunk_ids,
            ),
            _build_manager_deps(observer),
        )
    except ManagerError as exc:
        _end_trace(root_trace, error=_root_trace_error(exc))
        raise _http_error(exc) from exc

    # Grounding-floor abstain (Phase 4 query-UX): a valid outcome, not an error.
    # Return a 200 the frontend renders as an assistant message, with the nudge
    # and disclaimer attached — never a 422 red error.
    if plan.abstained:
        return _build_abstain_response(
            body, plan, root_trace, background_tasks, current_user, started_at
        )

    result = plan.retrieval
    gen = plan.generation
    permit_types = plan.permit_types
    conflict_warnings = [ConflictWarning(**w) for w in plan.conflict_warnings]

    # 3. Build response
    all_chunks = [
        ChunkResponse(
            id=chunk["id"],
            document_id=chunk["document_id"],
            doc_id=chunk["doc_id"],
            chunk_index=chunk["chunk_index"],
            content=chunk["content"],
            municipality=chunk["municipality"],
            authority_level=chunk["authority_level"],
            doc_type=chunk["doc_type"],
            document_status=chunk["document_status"],
            source_tier=chunk.get("source_tier", 1),
            similarity=chunk.get("raw_similarity") or chunk["similarity"],
            raw_similarity=chunk.get("raw_similarity", chunk["similarity"]),
            reranked_score=chunk.get("reranked_score", chunk["similarity"]),
            provenance_weight=chunk.get("provenance_weight", 1.0),
            filtered_out=chunk.get("filtered_out", False),
        )
        for chunk in result.chunks
    ]

    citations = [
        CitationResponse(
            doc_id=c["doc_id"],
            chunk_index=c["chunk_index"],
            found_in_context=c["found_in_context"],
            municipality=c.get("municipality"),
            authority_level=c.get("authority_level"),
        )
        for c in gen.citations
    ]

    # Sprint 6 — Fix 2: filter response chunks to only those cited (found_in_context=True).
    # Falls back to all retrieved chunks when no citations matched context.
    cited_keys: set[tuple[str, int]] = {
        (c["doc_id"], c["chunk_index"])
        for c in gen.citations
        if c["found_in_context"]
    }
    if cited_keys:
        cited_chunks = [
            cr for cr in all_chunks
            if (cr.doc_id, cr.chunk_index) in cited_keys
        ]
        log.info(
            "Fix2 citation filter: %d/%d chunks retained (cited by answer)",
            len(cited_chunks),
            len(all_chunks),
        )
    else:
        # No citations matched context — return everything so the caller
        # still has the retrieval context for inspection/debugging.
        cited_chunks = all_chunks
        log.info(
            "Fix2 citation filter: no in-context citations found — returning all %d chunks",
            len(all_chunks),
        )

    # Task 16F: tag cited chunks in Neo4j graph (background, non-blocking)
    if cited_keys:
        try:
            from db import graph_client as _gc
            background_tasks.add_task(
                _gc.record_cited_chunks,
                query_text=body.query,
                session_id=session_id,
                cited_pairs=list(cited_keys),
                cited_at_iso=datetime.now(UTC).isoformat(),
            )
        except Exception as exc:
            log.warning("16F: could not schedule graph enrichment task: %s", exc)

    diagnostics = DiagnosticsResponse(
        top_similarity=result.top_similarity,
        mean_similarity=result.mean_similarity,
        unique_doc_count=len(result.unique_documents),
        unique_doc_ids=result.unique_documents,
    )

    response = AnswerResponse(
        query=body.query,
        answer=gen.answer,
        citations=citations,
        model=gen.model,
        input_tokens=gen.input_tokens,
        output_tokens=gen.output_tokens,
        latency_generation_ms=gen.latency_ms,
        latency_retrieval_ms=result.latency_ms,
        num_chunks=gen.chunk_count,
        total_chunks_retrieved=len(all_chunks),
        chunks=cited_chunks,
        diagnostics=diagnostics,
        permit_types=permit_types,
        ahj_disclaimer=_build_ahj_disclaimer(plan.effective_municipality),
        resolved_municipality=plan.resolved_municipality,
        conflict_warnings=conflict_warnings,
        persona_nudge=_nudge_for(plan),
    )
    # Insert query log in Postgres (background, non-blocking)
    try:
        from db import client as db_client
        background_tasks.add_task(
            db_client.insert_query_log,
            query_text=body.query,
            model=gen.model,
            municipality=body.municipality,
            top_k=body.top_k,
            chunk_ids=[c.id for c in cited_chunks],
            answer_text=gen.answer,
            citations=[c.model_dump() for c in citations],
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            user_id=current_user["user_id"] if (current_user and isinstance(current_user, dict)) else None,
            project_id=UUID(body.project_id) if body.project_id else None,
        )
    except Exception as exc:
        log.warning("could not schedule Postgres query logging task: %s", exc)

    _end_trace(
        root_trace,
        outputs={
            "session_id": session_id,
            "request_id": request_id,
            "citation_count": len(citations),
            "latency_total_ms": int((time.perf_counter() - started_at) * 1000),
            "latency_retrieval_ms": result.latency_ms,
            "latency_generation_ms": gen.latency_ms,
            "top_similarity": result.top_similarity,
            "unique_doc_ids": result.unique_documents,
        },
    )
    return response


@router.get("/query/history", response_model=list[dict])
def get_query_history(
    current_user: Annotated[dict, Depends(get_current_user)],
    project_id: UUID | None = None,
) -> list[dict]:
    """Fetch the authenticated user's private query history."""
    from db import client as db_client
    rows = db_client.get_user_query_history(current_user["user_id"], project_id=project_id)
    return [dict(r) for r in rows]


@router.delete("/query/history/{query_id}", status_code=200)
def delete_query_history(query_id: UUID, current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Delete a specific query log entry from user history."""
    from db import client as db_client
    if not db_client.delete_user_query(current_user["user_id"], query_id):
        raise HTTPException(status_code=404, detail="Query log entry not found or unauthorized.")
    return {"detail": "Query log entry deleted successfully."}
