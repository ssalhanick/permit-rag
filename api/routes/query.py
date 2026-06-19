"""
api/routes/query.py — POST /query and POST /query/answer endpoints
====================================================================
/query: retrieval only — returns ranked chunks with metadata.
/query/answer: retrieval + generation — returns a cited answer from Claude.

Import boundary: api/ → rag/, db/, audit/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from api.auth import get_optional_current_user, get_current_user
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
from db.client import get_jurisdiction
from rag.retriever import retrieve

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
def query_answer(
    body: QueryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> AnswerResponse:
    """Retrieve chunks and generate a cited answer via Claude."""
    from rag.generator import generate_answer
    from rag.permit_classifier import classify_permit_types

    started_at = time.perf_counter()
    session_id = request.headers.get("X-Client-Session-Id", "").strip() or "unknown"
    request_id = request.headers.get("X-Client-Request-Id", "").strip() or f"api-{int(time.time() * 1000)}"
    tracing_on = _langsmith_enabled()

    # Sprint 3 Task 11: classify permit types (non-blocking)
    try:
        permit_types = classify_permit_types(body.query)
        log.info("permit_types detected: %s", permit_types)
    except Exception as exc:
        log.warning("permit_classifier failed (%s) — defaulting to []", exc)
        permit_types = []

    # Sprint 5 Task 14C: auto-resolve municipality from address when not explicit
    resolved_municipality: str | None = None
    effective_municipality = body.municipality
    if not effective_municipality and body.address:
        try:
            from rag.jurisdiction_resolver import municipality_from_address
            resolved = municipality_from_address(body.address)
            if resolved:
                resolved_municipality = resolved
                effective_municipality = resolved
                log.info(
                    "address geocoded to municipality='%s' for address=%r",
                    resolved, body.address,
                )
            else:
                log.info("address geocoding returned no match for %r", body.address)
        except Exception as exc:
            log.warning("jurisdiction_resolver failed (%s) — skipping auto-municipality", exc)

    metadata = {}
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

    # 1. Retrieve
    retrieval_trace = _start_trace(
        name="api_retrieval",
        run_type="tool",
        inputs={"query": body.query, "municipality": effective_municipality, "top_k": body.top_k},
        parent=root_trace,
    ) if tracing_on else None
    try:
        result = retrieve(
            body.query,
            top_k=body.top_k,
            municipality=effective_municipality,
            min_similarity=body.min_similarity,
        )
        _end_trace(
            retrieval_trace,
            outputs={
                "num_results": result.num_results,
                "top_similarity": result.top_similarity,
                "latency_retrieval_ms": result.latency_ms,
                "unique_doc_ids": result.unique_documents,
            },
        )
    except Exception as exc:
        log.exception("Retrieval failed for query: %s", body.query)
        _end_trace(retrieval_trace, error=f"Retrieval error: {exc}")
        _end_trace(root_trace, error=f"Retrieval error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval error: {exc}",
        ) from exc

    if not result.chunks:
        _end_trace(root_trace, error="No relevant chunks found.")
        raise HTTPException(
            status_code=404,
            detail="No relevant chunks found for this query.",
        )

    if (
        result.num_results < MIN_GROUNDED_CHUNKS
        or result.top_similarity < MIN_GROUNDED_TOP_SIM
    ):
        low_conf_msg = (
            "Insufficient retrieval confidence for grounded answer. "
            f"chunks={result.num_results}, top_similarity={result.top_similarity:.4f}, "
            f"required_chunks>={MIN_GROUNDED_CHUNKS}, "
            f"required_top_similarity>={MIN_GROUNDED_TOP_SIM:.2f}"
        )
        _end_trace(root_trace, error=low_conf_msg)
        raise HTTPException(
            status_code=422,
            detail=low_conf_msg,
        )

    # Sprint 5 Task 15: lightweight conflict detection (non-blocking)
    conflict_warnings: list[ConflictWarning] = []
    try:
        from rag.conflict_detector import detect_conflicts
        raw_conflicts = detect_conflicts(result.chunks)
        conflict_warnings = [
            ConflictWarning(
                subject=c.subject,
                chunk_a_doc_id=c.chunk_a.get("doc_id", ""),
                chunk_a_index=int(c.chunk_a.get("chunk_index", 0)),
                chunk_a_authority=str(c.chunk_a.get("authority_level", "")),
                chunk_b_doc_id=c.chunk_b.get("doc_id", ""),
                chunk_b_index=int(c.chunk_b.get("chunk_index", 0)),
                chunk_b_authority=str(c.chunk_b.get("authority_level", "")),
                detail=c.detail,
            )
            for c in raw_conflicts
        ]
        if conflict_warnings:
            log.info("conflict_warnings: %d conflict(s) detected", len(conflict_warnings))
    except Exception as exc:
        log.warning("conflict_detector failed (%s) — skipping", exc)

    # 2. Generate answer
    generation_trace = _start_trace(
        name="api_generation",
        run_type="llm",
        inputs={
            "query": body.query,
            "session_id": session_id,
            "request_id": request_id,
            "num_chunks": result.num_results,
        },
        parent=root_trace,
    ) if tracing_on else None
    try:
        gen = generate_answer(body.query, result.chunks)
        _end_trace(
            generation_trace,
            outputs={
                "model": gen.model,
                "input_tokens": gen.input_tokens,
                "output_tokens": gen.output_tokens,
                "latency_generation_ms": gen.latency_ms,
                "citation_count": len(gen.citations),
            },
        )
    except RuntimeError as exc:
        # ANTHROPIC_API_KEY not set
        log.error("Generator config error: %s", exc)
        _end_trace(generation_trace, error=str(exc))
        _end_trace(root_trace, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.exception("Generation failed for query: %s", body.query)
        _end_trace(generation_trace, error=f"Generation error: {exc}")
        _end_trace(root_trace, error=f"Generation error: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Generation error: {exc}",
        ) from exc

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
                cited_at_iso=datetime.now(timezone.utc).isoformat(),
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
        ahj_disclaimer=_build_ahj_disclaimer(effective_municipality),
        resolved_municipality=resolved_municipality,
        conflict_warnings=conflict_warnings,
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
def get_query_history(current_user: Annotated[dict, Depends(get_current_user)]) -> list[dict]:
    """Fetch the authenticated user's private query history."""
    from db import client as db_client
    rows = db_client.get_user_query_history(current_user["user_id"])
    return [dict(r) for r in rows]


@router.delete("/query/history/{query_id}", status_code=200)
def delete_query_history(query_id: UUID, current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Delete a specific query log entry from user history."""
    from db import client as db_client
    if not db_client.delete_user_query(current_user["user_id"], query_id):
        raise HTTPException(status_code=404, detail="Query log entry not found or unauthorized.")
    return {"detail": "Query log entry deleted successfully."}
