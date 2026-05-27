"""
api/routes/query.py — POST /query endpoint
============================================
Accepts a natural-language question, calls rag.retriever.retrieve(),
and returns ranked chunks with metadata and diagnostics.

Import boundary: api/ → rag/, db/, audit/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from api.schemas import (
    ChunkResponse,
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
