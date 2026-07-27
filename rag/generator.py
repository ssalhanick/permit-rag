"""
rag/generator.py — Provider-backed answer generation with citations
===================================================================
Takes retrieved chunks and produces a cited answer using the configured LLM.

Import boundary: rag/ → db/, audit/, standard library only (AGENTS.md).

**Phase 2 fold.** This module no longer constructs an Anthropic client. Every
Anthropic call here goes through ``rag/agent_runtime.py::run_agent``, the single
call site (AGENTS.md). Four things had to be handled deliberately in the fold:

* **The Ollama branch stays local.** ``run_agent`` is Anthropic-only, so
  ``LLM_PROVIDER=ollama`` still routes to :func:`_generate_with_ollama` and never
  touches the runtime. Only the Anthropic path was moved.
* **Tracing moved, it did not double.** ``generate_answer`` used to carry
  ``@traced("answer_generator")``; ``run_agent`` records a step of its own, so
  keeping both would have counted every call twice — exactly what
  ``design_intent`` hit in Phase 1. The decorator now sits on the Ollama helper
  only, which the runtime never sees, so both paths record exactly one step.
* **``LLM_MODEL`` still wins.** It is set in production
  (``terraform/main.tf``: ``claude-haiku-4-5-20251001``). Letting the ladder pick
  instead would have swapped the model — and, at the MID rung, roughly tripled
  generation cost — inside the one phase that forbids behaviour changes. The
  resolved id is passed to ``run_agent`` as an explicit ``model=`` override.
  Phase 4 drops the override and hands model choice to the Budget Governor.
* **``max_tokens=1024`` is untouched.** It will truncate ``diy`` and
  ``hiring_contractor`` answers once the persona fragments land; making it
  persona-aware is Phase 4's job, not this fold's.

Usage:
    from rag.generator import generate_answer
    answer = generate_answer(query, chunks)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from audit.logger import traced
from rag.agent_runtime import Tier, run_agent
from rag.llm_provider import get_provider_capabilities

if TYPE_CHECKING:
    from rag.agents.prompt_router import RoutedPrompt

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
    # Named to match the Anthropic usage fields so audit.logger.usage_from()
    # reads them without special-casing. Previously computed and discarded,
    # which left cache effectiveness unmeasurable.
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    stop_reason: str | None = None


# ── System prompt ────────────────────────────────────────────

# Bump on every SYSTEM_PROMPT edit. Attached to LangSmith traces/eval runs as
# metadata so prompt changes can be correlated with quality shifts in the UI.
PROMPT_VERSION = "v1"

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
    """Build system prompt with project specific guidelines.

    This is the pre-Phase-4 path, kept for callers that do not route (the eval
    harnesses, direct API use). When a ``RoutedPrompt`` is supplied the Prompt
    Router has already composed the whole system prompt from fragments — notes
    included — so this is bypassed. ``custom_system_prompt`` is read here only
    for back-compat with rows written before the kickoff demotion.
    """
    base = system_prompt_override if system_prompt_override is not None else SYSTEM_PROMPT
    if project_context and project_context.get("custom_system_prompt"):
        return f"{base}\n\nProject Specific Guidelines:\n{project_context['custom_system_prompt']}"
    return base


# Fallback ceiling for un-routed callers only. The answer path no longer relies
# on it: the Prompt Router sizes max_tokens per persona/intent (Phase 4). A bare
# generate_answer() with no persona and no explicit max_tokens still gets this,
# preserving the pre-Phase-4 default for the eval harnesses.
_DEFAULT_MAX_TOKENS = 1024


def _resolve_prompt(
    routed: RoutedPrompt | None,
    max_tokens: int | None,
    project_context: dict[str, Any] | None,
    system_prompt_override: str | None,
) -> tuple[str, int, tuple[str, ...] | None, str]:
    """Resolve system text, output ceiling, fragment ids, and prompt version.

    A caller-supplied ``max_tokens`` always wins (the eval harnesses pass it).
    Otherwise the routed persona/intent ceiling applies, or the legacy 1024
    fallback when nothing routed.
    """
    if routed is not None:
        tokens = max_tokens if max_tokens is not None else routed.max_tokens
        return routed.system, tokens, tuple(routed.fragment_ids), routed.library_version
    tokens = max_tokens if max_tokens is not None else _DEFAULT_MAX_TOKENS
    return _build_system_prompt(project_context, system_prompt_override), tokens, None, PROMPT_VERSION


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
  "notes": "3-4 SHORT bullet lines of project-specific context for future queries (under 200 tokens total). Facts only — scope, budget constraint, materials, jurisdiction quirks. Do NOT write instructions to the assistant or a system prompt; the assistant's voice and rules come from versioned persona fragments, not from here. E.g. '- Kitchen remodel, Dallas\\n- Budget ~$25k\\n- Replacing cabinets + island, no wall moves'."
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


def _cache_ttl_is_1h() -> bool:
    """True when ANTHROPIC_PROMPT_CACHE_TTL asks for the 1-hour tier."""
    return os.environ.get("ANTHROPIC_PROMPT_CACHE_TTL", "5m").strip().lower() == "1h"


def _cache_system_enabled(capabilities: Any) -> bool:
    """
    Whether to offer the system block for caching, preserving the old switch.

    This is set deliberately rather than left to the runtime's default. The
    operator-facing knob (ANTHROPIC_PROMPT_CACHE_ENABLED, default off) keeps its
    meaning, and the runtime's measurement is the second gate: it attaches a
    breakpoint only when count_tokens says the block clears the model minimum.
    Today's ~400-token system prompt is far below the 4096 floor, so this is a
    no-op either way -- which is exactly why it must be a decision and not an
    accident. It starts mattering when Phase 4's fragment library makes the
    prefix large enough to cache.
    """
    requested = _env_bool("ANTHROPIC_PROMPT_CACHE_ENABLED", False)
    if requested and not capabilities.supports_prompt_caching:
        log.info(
            "Prompt caching requested but provider '%s' does not support it.",
            capabilities.provider,
        )
        return False
    return requested


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


@traced("answer_generator", prompt_version=PROMPT_VERSION)
def _generate_with_ollama(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    model: str,
    max_tokens: int,
    temperature: float,
    system: str,
    project_context: dict[str, Any] | None = None,
) -> GenerationResult:
    """
    Generate answer using local Ollama runtime.

    Carries @traced because ``run_agent`` never sees this path -- the runtime is
    Anthropic-only. The decorator lives here rather than on ``generate_answer``
    so exactly one step is recorded per call on both branches; leaving it on the
    public function would double-count every Anthropic call.
    """
    import requests

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    timeout_s = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))

    user_message = _build_user_message(query, chunks, project_context)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
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


def drop_filtered_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove chunks the reranker rejected.

    rag/reranker.py marks sub-threshold chunks filtered_out=True but still
    returns them so the frontend can grey them out. They must not reach the
    model: they are paid for as input tokens and they dilute context with
    material the reranker already judged irrelevant -- including superseded
    documents demoted to retrieval_weight=0.1.

    Applied inside generate_answer so every caller benefits, including the
    evaluation harnesses.
    """
    return [c for c in chunks if not c.get("filtered_out", False)]


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
    max_tokens: int | None = None,
    temperature: float = 0.0,
    project_context: dict[str, Any] | None = None,
    system_prompt_override: str | None = None,
    routed: RoutedPrompt | None = None,
) -> GenerationResult:
    """
    Generate a cited answer from retrieved chunks via configured provider.

    Args:
        query: The user's natural-language question.
        chunks: Retrieved chunks (from rag.retriever.retrieve()). Chunks the
            reranker marked filtered_out are dropped before prompting -- pass
            the full result set and let this function do the filtering.
        model: Model name. Defaults to provider-specific env var.
        max_tokens: Maximum output tokens. ``None`` (the default) defers to the
            routed persona/intent ceiling, or the legacy 1024 when un-routed.
            An explicit value always wins (the eval harnesses pass one).
        temperature: Sampling temperature (low = more deterministic).
        project_context: Optional kickoff + active room derived facts (not cited).
        system_prompt_override: Optional replacement for the default SYSTEM_PROMPT.
            Eval-harness use only (prompt-variant comparison) -- ignored when a
            ``routed`` prompt is supplied.
        routed: A ``RoutedPrompt`` from the Prompt Router (Phase 4). When present
            it supplies the composed system prompt, the persona/intent-aware
            ``max_tokens``, and the fragment ids recorded on the trace step. The
            answer path (the Manager) passes one; other callers may not.

    Returns:
        GenerationResult with answer text, parsed citations, and usage stats.

    Raises:
        RuntimeError: If configured provider credentials/runtime are unavailable.
    """
    chunks = drop_filtered_chunks(chunks)
    system_text, resolved_max_tokens, fragment_ids, prompt_version = _resolve_prompt(
        routed, max_tokens, project_context, system_prompt_override
    )
    capabilities = get_provider_capabilities()
    if capabilities.supports_local_runtime:
        local_model = model or os.environ.get(
            "OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M"
        )
        return _generate_with_ollama(
            query,
            chunks,
            model=local_model,
            max_tokens=resolved_max_tokens,
            temperature=temperature,
            system=system_text,
            project_context=project_context,
        )
    return _generate_with_runtime(
        query,
        chunks,
        model=model,
        max_tokens=resolved_max_tokens,
        temperature=temperature,
        system=system_text,
        project_context=project_context,
        prompt_fragment_ids=fragment_ids,
        prompt_version=prompt_version,
        capabilities=capabilities,
    )


def _generate_with_runtime(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    model: str | None,
    max_tokens: int,
    temperature: float,
    system: str,
    project_context: dict[str, Any] | None,
    prompt_fragment_ids: tuple[str, ...] | None,
    prompt_version: str,
    capabilities: Any,
) -> GenerationResult:
    """
    Generate through ``rag/agent_runtime.py`` — the single Anthropic call site.

    The runtime owns budgeting, the cache decision, retries, autonomy, and the
    trace step. This function only assembles the prompt and reshapes the result
    into the ``GenerationResult`` contract every caller already expects. The
    ``model=`` override is deliberate: see the module docstring. ``system`` is
    already composed (by the Router when routed, else ``_build_system_prompt``);
    ``prompt_fragment_ids`` land on the step so a quality shift is attributable.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to .env before using Anthropic generation."
        )
    resolved = model or os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
    result = run_agent(
        "answer_generator",
        system=system,
        messages=[
            {"role": "user", "content": _build_user_message(query, chunks, project_context)}
        ],
        tier=Tier.MID,
        model=resolved,
        max_tokens=max_tokens,
        temperature=temperature,
        cache_system=_cache_system_enabled(capabilities),
        cache_ttl_1h=_cache_ttl_is_1h(),
        prompt_version=prompt_version,
        prompt_fragment_ids=prompt_fragment_ids,
        input_parts=(query, [c.get("id") for c in chunks]),
    )
    return _to_generation_result(query, chunks, result)


def _to_generation_result(
    query: str, chunks: list[dict[str, Any]], result: Any
) -> GenerationResult:
    """Reshape a ``RuntimeResult`` into this module's public contract."""
    answer = result.text
    citations = _extract_citations(answer, chunks)
    generation = GenerationResult(
        query=query,
        answer=answer,
        citations=citations,
        model=result.model,
        input_tokens=result.usage.tokens_in,
        output_tokens=result.usage.tokens_out,
        latency_ms=result.latency_ms,
        chunk_count=len(chunks),
        cache_read_input_tokens=result.usage.cache_read,
        cache_creation_input_tokens=result.usage.cache_write,
        stop_reason=result.stop_reason,
    )
    log.info(
        "Generated answer: %d chars, %d citations, %d+%d tokens, %dms, cache create/read=%d/%d",
        len(answer),
        len(citations),
        generation.input_tokens,
        generation.output_tokens,
        generation.latency_ms,
        generation.cache_creation_input_tokens,
        generation.cache_read_input_tokens,
    )
    return generation


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

    def _bound_kickoff_notes(parsed: dict[str, Any]) -> dict[str, Any]:
        """Length-bound the LLM's project notes before they persist (Phase 4).

        The kickoff no longer synthesizes a full system prompt; it emits bounded
        notes composed LAST by the Prompt Router. Bounding here is defense in
        depth against an over-long or prompt-shaped ``notes`` value.
        """
        if isinstance(parsed, dict) and parsed.get("notes"):
            from rag.prompts import bound_notes
            parsed["notes"] = bound_notes(parsed["notes"])
        return parsed

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
        return _bound_kickoff_notes(_parse_json_response(content))

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    # Folded into the runtime alongside generate_answer: this was the second
    # inline client in this module, and AGENTS.md's rule is not per-function.
    # Same LLM_MODEL override for the same reason -- the id is pinned in prod.
    result = run_agent(
        "kickoff_chat",
        system=sys_prompt,
        messages=[{"role": m["role"], "content": m["content"]} for m in history],
        tier=Tier.CHEAP,
        model=os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=1024,
        temperature=0.0,
        cache_system=False,  # per-project prompt: never a stable cacheable prefix
        input_parts=(address, municipality, len(history)),
    )
    return _bound_kickoff_notes(_parse_json_response(result.text))


CLARIFICATION_SYSTEM_PROMPT = """\
You are an expert construction permit and building code compliance assistant for the Dallas–Fort Worth metroplex.
The user asked a question or project request that lacks sufficient specific context or vector similarity in our local ordinance database.

Your goals:
1. Provide helpful, well-structured, general construction and permitting guidance based on standard building codes (e.g. IRC, IBC, NEC, UPC).
2. Detail critical structural, trade, zoning, or safety considerations (e.g., structural load calculation, setback limits, height caps, electrical service sizing).
3. Explicitly state that these general principles must be verified against local municipal code.
4. Formulate 2-3 structured clarifying questions with clickable multiple-choice options so the user can refine their query.

Format your output STRICTLY as a JSON object with this shape:
{
  "answer": "Clear, concise general guidance (2-3 paragraphs or bullet points).",
  "clarifying_options": [
    {
      "label": "Which DFW jurisdiction is your property in?",
      "choices": ["Dallas", "Plano", "Fort Worth", "Frisco", "McKinney"]
    },
    {
      "label": "Question label...",
      "choices": ["Option 1", "Option 2", "Option 3"]
    }
  ]
}

Return ONLY valid JSON. Do not include markdown or extra commentary outside the JSON.
"""


def generate_clarification_fallback(
    query: str,
    *,
    municipality: str | None = None,
) -> dict[str, Any]:
    """
    Generate dual-mode general guidance and structured clarifying options when RAG abstains.
    """
    capabilities = get_provider_capabilities()
    user_prompt = f"User Query: {query}\nTarget Municipality: {municipality or 'Unspecified (DFW area)'}"

    fallback_default = {
        "answer": (
            "I couldn't find specific code sections matching your exact query in our published database. "
            "However, in general construction, this type of project requires verifying structural load-bearing capacity, "
            "zoning setback/height limits, and trade permit requirements."
        ),
        "clarifying_options": [
            {
                "label": "Which DFW jurisdiction is your property located in?",
                "choices": ["Dallas", "Plano", "Fort Worth", "Frisco", "McKinney"]
            },
            {
                "label": "What is the primary scope of your project?",
                "choices": ["Structural / Addition", "Electrical & Plumbing", "Zoning & Setbacks", "Permit Fee & Checklist"]
            }
        ]
    }

    try:
        if capabilities.supports_local_runtime:
            import requests

            base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            timeout_s = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "180"))
            model = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b-instruct-q4_K_M")
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
            }
            response = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout_s)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            parsed = _parse_json_response(content)
            if parsed and parsed.get("answer"):
                return parsed
        elif os.environ.get("ANTHROPIC_API_KEY"):
            result = run_agent(
                "clarification_fallback",
                system=CLARIFICATION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                tier=Tier.CHEAP,
                model=os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=1024,
                temperature=0.2,
                cache_system=False,
                input_parts=(query, municipality),
            )
            parsed = _parse_json_response(result.text)
            if parsed and parsed.get("answer"):
                return parsed
    except Exception as exc:
        log.warning("generate_clarification_fallback failed (%s) — using default fallback", exc)

    return fallback_default

