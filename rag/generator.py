"""
rag/generator.py — Provider-backed answer generation with citations
===================================================================
Takes retrieved chunks and produces a cited answer using the configured LLM.

Import boundary: rag/ → db/, audit/, standard library only (AGENTS.md).
All model calls go through this module exclusively (AGENTS.md).

Usage:
    from rag.generator import generate_answer
    answer = generate_answer(query, chunks)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

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
6. If context is insufficient, state that the question cannot be answered based on the available context and do not infer.
7. Keep answers concise and structured. Use bullet points for multi-part answers.
Output style:
- Start with a direct answer in 1-2 sentences when possible.
- Follow with 1-2short bullet points of supporting details.
- Include citations on claims that state requirements, limits, or conditions.
- Avoid generic background unless it is needed to interpret a cited requirement.
"""


def _build_system_prompt(
    project_context: dict[str, Any] | None = None,
    system_prompt_override: str | None = None,
) -> str:
    """Build system prompt with project specific guidelines."""
    base = system_prompt_override if system_prompt_override is not None else SYSTEM_PROMPT
    if project_context and project_context.get("custom_system_prompt"):
        return f"{base}\n\nProject Specific Guidelines:\n{project_context['custom_system_prompt']}"
    return base


KICKOFF_SYSTEM_PROMPT = """\
You are an expert construction permit assistant. You are guiding a user through setting up a new project.
We already know:
- Address: {address}
- Municipality: {municipality}
- Spaces involved: {spaces}
- Work types: {work_types}

Your goal is to converse with the user and determine:
1. Persona: Are they a DIYer (diy), hiring a contractor (hiring_contractor), a contractor themselves (contractor), or just doing research (research)?
2. Budget: What is their estimated budget?
3. Materials and Scope: Are there specific materials or structural scope details?

(Note: The user's persona may already be specified in the chat history. If so, do not ask about it, just extract it.)

Ask exactly one brief question at a time to gather missing details. Keep questions friendly, helpful, and under 2 sentences.

If and only if you have enough information about all three aspects (persona, budget, and scope), do NOT ask another question. Instead, output a JSON block with:
{{
  "is_complete": true,
  "persona": "diy" | "hiring_contractor" | "contractor" | "research",
  "budget": "extracted budget description",
  "custom_system_prompt": "A detailed system prompt containing 3-4 bullet guidelines for future RAG queries based on the project profile. E.g. 'DIYer compliance path', 'Include Texas code exceptions for homeowners', 'Budget constraints', 'Dallas kitchen clearances info'."
}}
Otherwise, output:
{{
  "is_complete": false,
  "next_question": "Your next follow-up question here"
}}

You must return ONLY a JSON object. Do not include markdown formatting or extra text outside the JSON.
"""



def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean environment variable values."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _prompt_cache_control() -> dict[str, str] | None:
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


def _build_user_message(
    query: str,
    chunks: list[dict[str, Any]],
    project_context: dict[str, Any] | None = None,
) -> str:
    """Assemble user message with optional project facts and retrieved chunks."""
    from rag.project_context import format_project_context_block

    context = _format_chunks_for_prompt(chunks)
    project_block = format_project_context_block(project_context)
    parts = [f"Question: {query}"]
    if project_block:
        parts.append(f"\n{project_block}")
    parts.append(f"\nContext ({len(chunks)} chunks):\n\n{context}")
    parts.append(
        "\nProvide a strictly grounded, cited answer based on the code context. "
        "Project measurements are supporting facts only — cite code chunks for requirements."
    )
    return "\n".join(parts)


def _generate_with_ollama(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    project_context: dict[str, Any] | None = None,
    system_prompt_override: str | None = None,
) -> GenerationResult:
    """Generate answer using local Ollama runtime."""
    import requests

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    timeout_s = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

    user_message = _build_user_message(query, chunks, project_context)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _build_system_prompt(project_context, system_prompt_override),
            },
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }

    t0 = time.perf_counter()
    response = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=timeout_s,
    )
    response.raise_for_status()
    body = response.json()
    latency_ms = int((time.perf_counter() - t0) * 1000)

    answer = body.get("message", {}).get("content", "")
    citations = _extract_citations(answer, chunks)
    input_tokens = int(body.get("prompt_eval_count") or 0)
    output_tokens = int(body.get("eval_count") or 0)
    used_model = str(body.get("model") or model)

    result = GenerationResult(
        query=query,
        answer=answer,
        citations=citations,
        model=used_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        chunk_count=len(chunks),
    )

    log.info(
        "Generated local answer: %d chars, %d citations, %d+%d tokens, %dms (%s)",
        len(answer),
        len(citations),
        result.input_tokens,
        result.output_tokens,
        result.latency_ms,
        used_model,
    )
    return result


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

    Accepts both citation formats (case-insensitive):
      Strict (comma): [dallas-building-code, chunk 42]
      Loose (space):  [dallas-building-code chunk 42]
                      [dallas-building-code, Chunk 42]   (capital C)

    Logs a warning when citations reference chunks not found in the
    retrieved context (possible hallucination or format drift).
    """
    import re

    citations: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Strict pattern — [doc_id, chunk N] (comma-separated)
    _strict = re.compile(r"\[([^,\]]+),\s*chunk\s*(\d+)\]", re.IGNORECASE)
    # Loose pattern  — [doc_id chunk N] (space only, no comma)
    _loose = re.compile(r"\[([^\]\s,]+)\s+chunk\s+(\d+)\]", re.IGNORECASE)

    raw_matches: list[tuple[str, int]] = []
    for m in _strict.finditer(answer):
        raw_matches.append((m.group(1).strip(), int(m.group(2))))
    for m in _loose.finditer(answer):
        pair = (m.group(1).strip(), int(m.group(2)))
        if pair not in raw_matches:
            raw_matches.append(pair)

    unmatched = 0
    for doc_id, chunk_idx in raw_matches:
        key = f"{doc_id}:{chunk_idx}"
        if key in seen:
            continue
        seen.add(key)

        source_chunk = next(
            (
                c for c in chunks
                if c.get("doc_id") == doc_id and c.get("chunk_index") == chunk_idx
            ),
            None,
        )
        if source_chunk is None:
            unmatched += 1

        citations.append({
            "doc_id": doc_id,
            "chunk_index": chunk_idx,
            "found_in_context": source_chunk is not None,
            "municipality": source_chunk.get("municipality") if source_chunk else None,
            "authority_level": source_chunk.get("authority_level") if source_chunk else None,
        })

    if unmatched:
        log.warning(
            "_extract_citations: %d/%d citations not matched to context chunks "
            "(possible hallucination or format drift — check LLM output)",
            unmatched,
            len(citations),
        )

    return citations


# ── Core generation function ─────────────────────────────────


def generate_answer(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    project_context: dict[str, Any] | None = None,
    system_prompt_override: str | None = None,
) -> GenerationResult:
    """
    Generate a cited answer from retrieved chunks via configured provider.

    Args:
        query: The user's natural-language question.
        chunks: Retrieved chunks (from rag.retriever.retrieve()).
        model: Model name. Defaults to provider-specific env var.
        max_tokens: Maximum output tokens.
        temperature: Sampling temperature (low = more deterministic).
        project_context: Optional kickoff + active room derived facts (not cited).
        system_prompt_override: Optional replacement for the default SYSTEM_PROMPT.
            Eval-harness use only (prompt-variant comparison) -- unset in all
            production call sites, so default behavior is unchanged.

    Returns:
        GenerationResult with answer text, parsed citations, and usage stats.

    Raises:
        RuntimeError: If configured provider credentials/runtime are unavailable.
    """
    capabilities = get_provider_capabilities()
    if capabilities.supports_local_runtime:
        local_model = model or os.environ.get(
            "OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M"
        )
        return _generate_with_ollama(
            query,
            chunks,
            model=local_model,
            max_tokens=max_tokens,
            temperature=temperature,
            project_context=project_context,
            system_prompt_override=system_prompt_override,
        )

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to .env before using Anthropic generation."
        )

    model = model or os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
    cache_requested = _env_bool("ANTHROPIC_PROMPT_CACHE_ENABLED", False)
    cache_enabled = cache_requested and capabilities.supports_prompt_caching
    if cache_requested and not capabilities.supports_prompt_caching:
        log.info(
            "Prompt caching requested but provider '%s' does not support it.",
            capabilities.provider,
        )

    # Format context
    user_message = _build_user_message(query, chunks, project_context)

    t0 = time.perf_counter()

    client = anthropic.Anthropic(api_key=api_key)
    cache_control = _prompt_cache_control()
    system_payload: Any
    system_prompt_str = _build_system_prompt(project_context, system_prompt_override)
    if cache_enabled:
        system_payload = [
            {
                "type": "text",
                "text": system_prompt_str,
                "cache_control": cache_control,
            }
        ]
    else:
        system_payload = system_prompt_str
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


def _parse_json_response(content: str) -> dict[str, Any]:
    """Parse JSON response from LLM, stripping markdown wrappers if present."""
    import json
    import re
    cleaned = content.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("Failed to parse LLM JSON: %r", content)
        return {
            "is_complete": False,
            "next_question": "Could you please tell me more details about your project persona and budget?",
        }


def generate_kickoff_chat_response(
    history: list[dict[str, str]],
    *,
    address: str | None = None,
    municipality: str | None = None,
    spaces: list[str] | None = None,
    work_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Drive the project kickoff chat.
    Uses LLM to decide if info is complete, ask the next question,
    or extract profile details + synthesize system prompt.
    """
    capabilities = get_provider_capabilities()

    spaces_str = ", ".join(spaces) if spaces else "None"
    work_types_str = ", ".join(work_types) if work_types else "None"
    sys_prompt = KICKOFF_SYSTEM_PROMPT.format(
        address=address or "Unknown",
        municipality=municipality or "Unknown",
        spaces=spaces_str,
        work_types=work_types_str,
    )

    if capabilities.supports_local_runtime:
        import requests

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        timeout_s = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")

        ollama_messages = [{"role": "system", "content": sys_prompt}]
        for msg in history:
            ollama_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "model": model,
            "messages": ollama_messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0.0,
            },
        }
        response = requests.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=timeout_s,
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        return _parse_json_response(content)

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    model = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
    client = anthropic.Anthropic(api_key=api_key)

    anthropic_messages = []
    for msg in history:
        anthropic_messages.append({"role": msg["role"], "content": msg["content"]})

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.0,
        system=sys_prompt,
        messages=anthropic_messages,
    )
    content = response.content[0].text
    return _parse_json_response(content)
