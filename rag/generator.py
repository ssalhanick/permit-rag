"""
rag/generator.py — Claude-powered answer generation with citations
===================================================================
Takes retrieved chunks and produces a cited answer using the Anthropic API.

Import boundary: rag/ → db/, audit/, standard library only (AGENTS.md).
All Anthropic calls go through this module exclusively (AGENTS.md).

Usage:
    from rag.generator import generate_answer
    answer = generate_answer(query, chunks)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger(__name__)


# ── Result dataclass ─────────────────────────────────────────


@dataclass
class GenerationResult:
    """Container for a single generation run."""

    query: str
    answer: str
    citations: list[dict[str, Any]]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    chunk_count: int


# ── System prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a construction permit compliance assistant for the Dallas–Fort Worth \
metropolitan area. You answer questions about building codes, permits, zoning, \
and regulatory requirements using ONLY the provided source chunks.

Rules:
1. Answer ONLY from the provided chunks. If the chunks don't contain enough \
   information, say so explicitly — never fabricate information.
2. Cite every factual claim using [doc_id, chunk N] format. Example: \
   [dallas-building-code-vol1, chunk 42].
3. If chunks from different sources conflict, flag the conflict explicitly \
   and cite both sources.
4. Never imply you have direct access to municipal authority. Always reference \
   the publisher and document.
5. Be concise but thorough. Use bullet points for multi-part answers.
6. If a question is ambiguous about which municipality, ask for clarification \
   or note which jurisdiction(s) the answer applies to.
"""


def _format_chunks_for_prompt(chunks: list[dict[str, Any]]) -> str:
    """Format retrieved chunks as numbered context blocks."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        doc_id = chunk.get("doc_id", "unknown")
        idx = chunk.get("chunk_index", "?")
        muni = chunk.get("municipality", "unknown")
        level = chunk.get("authority_level", "unknown")
        sim = chunk.get("similarity", 0.0)
        content = chunk.get("content", "")

        parts.append(
            f"--- Source {i} ---\n"
            f"doc_id: {doc_id}\n"
            f"chunk: {idx}\n"
            f"municipality: {muni}\n"
            f"authority_level: {level}\n"
            f"similarity: {sim:.4f}\n\n"
            f"{content}\n"
        )
    return "\n".join(parts)


def _extract_citations(
    answer: str,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract citation references from the generated answer.

    Looks for [doc_id, chunk N] patterns and matches them to
    the provided chunks for structured citation metadata.
    """
    import re

    citations: list[dict[str, Any]] = []
    seen: set[str] = set()

    pattern = re.compile(r"\[([^,\]]+),\s*chunk\s*(\d+)\]")
    for match in pattern.finditer(answer):
        doc_id = match.group(1).strip()
        chunk_idx = int(match.group(2))
        key = f"{doc_id}:{chunk_idx}"

        if key in seen:
            continue
        seen.add(key)

        # Find matching chunk in context
        source_chunk = None
        for c in chunks:
            if c.get("doc_id") == doc_id and c.get("chunk_index") == chunk_idx:
                source_chunk = c
                break

        citations.append({
            "doc_id": doc_id,
            "chunk_index": chunk_idx,
            "found_in_context": source_chunk is not None,
            "municipality": source_chunk.get("municipality") if source_chunk else None,
            "authority_level": source_chunk.get("authority_level") if source_chunk else None,
        })

    return citations


# ── Core generation function ─────────────────────────────────


def generate_answer(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.1,
) -> GenerationResult:
    """
    Generate a cited answer from retrieved chunks via Claude.

    Args:
        query: The user's natural-language question.
        chunks: Retrieved chunks (from rag.retriever.retrieve()).
        model: Claude model name. Defaults to LLM_MODEL env var.
        max_tokens: Maximum output tokens.
        temperature: Sampling temperature (low = more deterministic).

    Returns:
        GenerationResult with answer text, parsed citations, and usage stats.

    Raises:
        RuntimeError: If ANTHROPIC_API_KEY is not set.
        anthropic.APIError: On API failures.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to .env before using the generator."
        )

    model = model or os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")

    # Format context
    context = _format_chunks_for_prompt(chunks)
    user_message = (
        f"Question: {query}\n\n"
        f"Context ({len(chunks)} chunks):\n\n"
        f"{context}\n\n"
        f"Provide a thorough, cited answer based on the above context."
    )

    t0 = time.perf_counter()

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    answer = response.content[0].text
    citations = _extract_citations(answer, chunks)

    result = GenerationResult(
        query=query,
        answer=answer,
        citations=citations,
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
        chunk_count=len(chunks),
    )

    log.info(
        "Generated answer: %d chars, %d citations, %d+%d tokens, %dms",
        len(answer),
        len(citations),
        result.input_tokens,
        result.output_tokens,
        result.latency_ms,
    )

    return result
