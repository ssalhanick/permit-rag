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
from dataclasses import dataclass
from typing import Any, Optional

from rag.llm_provider import get_provider_capabilities

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
metropolitan area. Answer questions about permits, codes, zoning, and regulatory \
requirements using ONLY the provided source chunks.
Rules:
1. If support is partial, state uncertainty briefly, then provide only the supported points with citations.
2. Cite factual claims using [doc_id, chunk N] format. \
   Example: [dallas-building-code-vol1, chunk 42].
3. Prioritize direct, actionable requirements (thresholds, permit triggers, \
   exceptions, scope, authority).
4. If sources conflict, explicitly note the conflict and cite both sides.
5. If jurisdiction is ambiguous, state what jurisdiction the cited chunks appear \
   to apply to.
6. Keep answers concise and structured. Use bullet points for multi-part answers.
Output style:
- Start with a direct answer in 1-2 sentences when possible.
- Follow with short bullet points of supporting details.
- Include citations on claims that state requirements, limits, or conditions.
- Avoid generic background unless it is needed to interpret a cited requirement.
"""


def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean environment variable values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _prompt_cache_control() -> Optional[dict[str, str]]:
    """Build Anthropic cache_control payload from environment."""
    ttl = os.environ.get("ANTHROPIC_PROMPT_CACHE_TTL", "5m").strip().lower()
    if ttl not in {"5m", "1h"}:
        ttl = "5m"
    cache_control: dict[str, str] = {"type": "ephemeral"}
    if ttl == "1h":
        cache_control["ttl"] = "1h"
    return cache_control


def _extract_cache_tokens(usage: Any) -> tuple[int, int]:
    """Return (cache_creation_tokens, cache_read_tokens) from usage."""
    created = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    return created, read


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
    temperature: float = 0.0,
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
    capabilities = get_provider_capabilities()
    cache_requested = _env_bool("ANTHROPIC_PROMPT_CACHE_ENABLED", False)
    cache_enabled = cache_requested and capabilities.supports_prompt_caching
    if cache_requested and not capabilities.supports_prompt_caching:
        log.info(
            "Prompt caching requested but provider '%s' does not support it.",
            capabilities.provider,
        )

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
    cache_control = _prompt_cache_control()
    system_payload: Any
    if cache_enabled:
        system_payload = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": cache_control,
            }
        ]
    else:
        system_payload = SYSTEM_PROMPT
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_payload,
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
    cache_create_tokens, cache_read_tokens = _extract_cache_tokens(response.usage)

    log.info(
        "Generated answer: %d chars, %d citations, %d+%d tokens, %dms, cache create/read=%d/%d",
        len(answer),
        len(citations),
        result.input_tokens,
        result.output_tokens,
        result.latency_ms,
        cache_create_tokens,
        cache_read_tokens,
    )

    return result
