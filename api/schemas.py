"""
api/schemas.py — Pydantic models for request/response schemas
==============================================================
All API request and response bodies are defined here.
Keeps route files thin and enables OpenAPI schema generation.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request models ───────────────────────────────────────────


class QueryRequest(BaseModel):
    """Body for POST /query — maps to rag.retriever.retrieve() args."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural-language question about permit/code compliance.",
        json_schema_extra={"examples": ["What are the setback requirements for a residential fence in Dallas?"]},
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of chunks to retrieve.",
    )
    municipality: Optional[str] = Field(
        default=None,
        description="Optional municipality filter (e.g. 'dallas', 'plano').",
    )
    min_similarity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Discard results below this cosine similarity.",
    )


# ── Response models ──────────────────────────────────────────


class ChunkResponse(BaseModel):
    """A single retrieved chunk with metadata."""

    id: UUID = Field(description="Chunk primary key.")
    document_id: UUID = Field(description="Parent document UUID.")
    doc_id: str = Field(description="Human-readable document identifier.")
    chunk_index: int = Field(description="Position within the document.")
    content: str = Field(description="Chunk text content.")
    municipality: str = Field(description="Source municipality.")
    authority_level: str = Field(description="Authority level (municipal/state/federal).")
    doc_type: str = Field(description="Document type.")
    document_status: str = Field(description="Document status (active/superseded/repealed).")
    similarity: float = Field(description="Cosine similarity to the query (0–1).")


class DiagnosticsResponse(BaseModel):
    """Retrieval diagnostics for monitoring and evaluation."""

    top_similarity: float = Field(description="Highest similarity score.")
    mean_similarity: float = Field(description="Average similarity across returned chunks.")
    unique_doc_count: int = Field(description="Number of distinct source documents.")
    unique_doc_ids: list[str] = Field(description="List of distinct doc_id values.")


class QueryResponse(BaseModel):
    """Response for POST /query — ranked chunks with metadata."""

    query: str = Field(description="Original query string.")
    top_k: int = Field(description="Requested top_k.")
    municipality: Optional[str] = Field(description="Applied municipality filter.")
    num_results: int = Field(description="Number of chunks returned.")
    latency_ms: int = Field(description="End-to-end retrieval latency in milliseconds.")
    model: str = Field(description="Embedding model used.")
    chunks: list[ChunkResponse] = Field(description="Ranked chunks (descending similarity).")
    diagnostics: DiagnosticsResponse = Field(description="Retrieval quality diagnostics.")


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = Field(description="Service status: 'healthy' or 'unhealthy'.")
    database: bool = Field(description="True if the database is reachable.")
    version: str = Field(description="API version string.")


class CitationResponse(BaseModel):
    """A single citation extracted from the generated answer."""

    doc_id: str = Field(description="Human-readable document identifier.")
    chunk_index: int = Field(description="Chunk position within the document.")
    found_in_context: bool = Field(description="True if citation matched a retrieved chunk.")
    municipality: Optional[str] = Field(description="Source municipality.")
    authority_level: Optional[str] = Field(description="Authority level of cited source.")


class AnswerResponse(BaseModel):
    """Response for POST /query/answer — generated answer with citations."""

    query: str = Field(description="Original query string.")
    answer: str = Field(description="Claude-generated answer text with inline citations.")
    citations: list[CitationResponse] = Field(description="Structured citations extracted from the answer.")
    model: str = Field(description="LLM model used for generation.")
    input_tokens: int = Field(description="Prompt tokens consumed.")
    output_tokens: int = Field(description="Completion tokens consumed.")
    latency_generation_ms: int = Field(description="Generation latency in milliseconds.")
    latency_retrieval_ms: int = Field(description="Retrieval latency in milliseconds.")
    num_chunks: int = Field(description="Number of chunks sent to the generator.")
    chunks: list[ChunkResponse] = Field(description="Retrieved chunks used as context.")
    diagnostics: DiagnosticsResponse = Field(description="Retrieval quality diagnostics.")


class ErrorResponse(BaseModel):
    """Standard error response body."""

    detail: str = Field(description="Human-readable error description.")
