"""
api/routes/query.py — POST /query and POST /query/answer endpoints
====================================================================
/query: retrieval only — returns ranked chunks with metadata.
/query/answer: retrieval + generation — returns a cited answer from Claude.

Import boundary: api/ → rag/, db/, audit/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.schemas import (
    AnswerResponse,
    ChunkResponse,
    CitationResponse,
    DiagnosticsResponse,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)
from rag.retriever import retrieve

log = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


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
def query_chunks(body: QueryRequest) -> QueryResponse:
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
            similarity=chunk["similarity"],
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
        422: {"model": ErrorResponse, "description": "Validation error"},
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
def query_answer(body: QueryRequest) -> AnswerResponse:
    """Retrieve chunks and generate a cited answer via Claude."""
    from rag.generator import generate_answer

    # 1. Retrieve
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

    if not result.chunks:
        raise HTTPException(
            status_code=404,
            detail="No relevant chunks found for this query.",
        )

    # 2. Generate answer
    try:
        gen = generate_answer(body.query, result.chunks)
    except RuntimeError as exc:
        # ANTHROPIC_API_KEY not set
        log.error("Generator config error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        log.exception("Generation failed for query: %s", body.query)
        raise HTTPException(
            status_code=500,
            detail=f"Generation error: {exc}",
        ) from exc

    # 3. Build response
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
            similarity=chunk["similarity"],
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

    diagnostics = DiagnosticsResponse(
        top_similarity=result.top_similarity,
        mean_similarity=result.mean_similarity,
        unique_doc_count=len(result.unique_documents),
        unique_doc_ids=result.unique_documents,
    )

    return AnswerResponse(
        query=body.query,
        answer=gen.answer,
        citations=citations,
        model=gen.model,
        input_tokens=gen.input_tokens,
        output_tokens=gen.output_tokens,
        latency_generation_ms=gen.latency_ms,
        latency_retrieval_ms=result.latency_ms,
        num_chunks=gen.chunk_count,
        chunks=chunks,
        diagnostics=diagnostics,
    )
