"""
rag/agent_runtime.py — the single Anthropic call site
=====================================================
Phase 1 of the agent architecture. Every model call in the RAG core goes
through :func:`run_agent`. Before Phase 1 two places built an Anthropic client
directly (``rag/generator.py`` and ``rag/design_intent.py``); each independently
decided the model, ``max_tokens``, caching, retries, and whether anything was
traced. One call site means one place to change the model ladder, one place that
can forget a trace (it can't), and one place that enforces autonomy.

What this module owns, in one place:

* **Structured outputs** — native ``client.messages.parse(output_format=Model)``
  → ``response.parsed_output``. Guaranteed schema validity, no JSON-repair
  retries. (We deliberately do not add the ``instructor`` dependency; pydantic
  is already present.)
* **The model ladder** — cheap = haiku, mid = sonnet, top = opus, with
  ``output_config={"effort": "low"}`` on cheap-tier subagent calls.
* **Prompt caching** — a ``cache_control`` breakpoint is attached to the system
  block *only* when it clears the model's minimum cacheable prefix (4096 tokens
  on Haiku/Opus, 2048 on Sonnet). Below that, a breakpoint silently no-ops
  (``cache_creation_input_tokens: 0``, no error), so we measure first.
* **Token budgeting** — ``client.messages.count_tokens`` pre-flight. Never
  ``tiktoken`` (it undercounts Claude 15-20%).
* **Automatic tracing** — every call records a step through ``audit.logger``.
* **Autonomy enforcement** — the check lives here so it is unbypassable from the
  first agent. Agents absent from ``agent_autonomy`` default to L0 (fail closed).
* **Retries** — transient API failures back off and retry.

Import boundary: rag/ → db/, audit/, standard library (+ anthropic, pydantic).
AGENTS.md's "no inline anthropic calls" rule now permits exactly this module.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from audit.logger import StepUsage, input_hash, record_step, usage_from
from db import client as db_client

log = logging.getLogger(__name__)


# ── Model ladder ─────────────────────────────────────────────


class Tier(StrEnum):
    """The three rungs of the model ladder (docs/agent_architecture.md)."""

    CHEAP = "cheap"
    MID = "mid"
    TOP = "top"


_LADDER: dict[Tier, str] = {
    Tier.CHEAP: "claude-haiku-4-5",
    Tier.MID: "claude-sonnet-5",
    Tier.TOP: "claude-opus-4-8",
}


def model_for_tier(tier: Tier) -> str:
    """Return the model id for a ladder tier."""
    return _LADDER[tier]


# ── Prompt caching ───────────────────────────────────────────
# Minimum cacheable prefix in tokens. A cache_control breakpoint on a block
# smaller than this is silently ignored — the single most expensive footgun in
# the caching API. Keyed by model-family prefix; longest match wins.

_MIN_CACHE_PREFIX: dict[str, int] = {
    "claude-haiku": 4096,
    "claude-opus": 4096,
    "claude-sonnet": 2048,
}
_DEFAULT_MIN_CACHE_PREFIX = 4096


def min_cache_prefix(model: str) -> int:
    """Smallest system-block size (tokens) that actually caches on this model."""
    for key in sorted(_MIN_CACHE_PREFIX, key=len, reverse=True):
        if model.startswith(key):
            return _MIN_CACHE_PREFIX[key]
    return _DEFAULT_MIN_CACHE_PREFIX


# ── Autonomy ─────────────────────────────────────────────────

_AUTONOMY_ORDER: dict[str, int] = {"L0": 0, "L1": 1, "L2": 2, "L3": 3}
_DEFAULT_AUTONOMY = "L0"  # fail closed: an unregistered agent has no authority


class AutonomyError(RuntimeError):
    """Raised when an agent requests an action above its current autonomy."""


class BudgetError(RuntimeError):
    """Raised when a request's counted input tokens exceed its budget."""


def resolve_autonomy_level(agent_name: str, scope: str = "default") -> str:
    """
    Return an agent's effective autonomy level, never above its ceiling.

    An agent with no ``agent_autonomy`` row resolves to L0 (fail closed), so a
    new agent cannot act until an operator deliberately grants it authority. The
    stored ``current_level`` is also capped at ``max_level`` defensively — the
    SQL setter clamps on write, but reading is the last line of defence.
    """
    try:
        row = db_client.get_agent_autonomy(agent_name, scope)
    except Exception as exc:  # a trace/DB blip must not grant authority
        log.warning("autonomy lookup failed for %s/%s (%s); defaulting L0",
                    agent_name, scope, exc)
        return _DEFAULT_AUTONOMY
    if not row:
        return _DEFAULT_AUTONOMY
    current = str(row.get("current_level") or _DEFAULT_AUTONOMY)
    ceiling = str(row.get("max_level") or _DEFAULT_AUTONOMY)
    if _AUTONOMY_ORDER.get(current, 0) > _AUTONOMY_ORDER.get(ceiling, 0):
        return ceiling
    return current


def enforce_autonomy(
    agent_name: str, required_level: str, *, scope: str = "default"
) -> str:
    """
    Assert an agent may act at ``required_level``; raise ``AutonomyError`` if not.

    This is the primitive every side-effecting agent calls before it acts. It
    lives in the runtime, not the dashboard, so the check cannot be bypassed —
    the dashboard only edits the value this function reads.
    """
    effective = resolve_autonomy_level(agent_name, scope)
    if _AUTONOMY_ORDER.get(effective, 0) < _AUTONOMY_ORDER.get(required_level, 99):
        raise AutonomyError(
            f"{agent_name}/{scope} is at {effective}; action needs {required_level}"
        )
    return effective


# ── Anthropic client ─────────────────────────────────────────

# Transient failures worth a backoff-and-retry. A 4xx (bad request, auth) is not
# here — retrying it just wastes time.
def _retryable_errors() -> tuple[type[Exception], ...]:
    """
    Anthropic exception classes that a retry might clear (import-lazy).

    Resolved by name so the tuple degrades gracefully across SDK versions --
    older anthropic releases lack ``OverloadedError`` / ``InternalServerError``,
    and referencing them directly raised ``AttributeError`` at call time.
    """
    import anthropic

    names = (
        "RateLimitError", "APIConnectionError", "APITimeoutError",
        "InternalServerError", "OverloadedError",
    )
    resolved: list[type[Exception]] = []
    for name in names:
        cls = getattr(anthropic, name, None)
        if isinstance(cls, type):
            resolved.append(cls)
    return tuple(resolved) or (anthropic.APIError,)


def _build_client(client: Any | None) -> Any:
    """Return the injected client, or construct one from ANTHROPIC_API_KEY."""
    if client is not None:
        return client
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to .env before calling an agent."
        )
    return anthropic.Anthropic(api_key=api_key)


def _count_tokens(
    client: Any, model: str, *, system: Any, messages: list[dict[str, Any]]
) -> int | None:
    """
    Pre-flight input-token count, or None if the counter is unavailable.

    Returns None (rather than a guess) on failure — callers then skip budget
    enforcement and skip caching, both safe. We never fall back to tiktoken.
    """
    try:
        resp = client.messages.count_tokens(model=model, system=system, messages=messages)
        return int(resp.input_tokens)
    except Exception as exc:
        log.info("count_tokens unavailable for %s (%s); skipping preflight", model, exc)
        return None


# ── Request assembly ─────────────────────────────────────────


def _cache_control(cache_ttl_1h: bool) -> dict[str, Any]:
    """Ephemeral cache_control payload; 1-hour TTL for stable corpus blocks."""
    control: dict[str, Any] = {"type": "ephemeral"}
    if cache_ttl_1h:
        control["ttl"] = "1h"
    return control


def _system_payload(
    system: str | Sequence[dict[str, Any]],
    *,
    cache: bool,
    cache_ttl_1h: bool,
    caches_ok: bool,
) -> str | list[dict[str, Any]]:
    """
    Build the ``system`` field, attaching a cache breakpoint only when it works.

    ``caches_ok`` is the measured verdict that the block clears the model's
    minimum prefix. A pre-structured list is passed through untouched — the
    caller has taken control of its own breakpoints.
    """
    if not isinstance(system, str):
        return list(system)
    if cache and caches_ok:
        return [{"type": "text", "text": system,
                 "cache_control": _cache_control(cache_ttl_1h)}]
    return system


def _output_config(effort: str | None) -> dict[str, Any] | None:
    """Assemble ``output_config`` (currently just the effort knob), or None."""
    return {"effort": effort} if effort else None


def _extract_text(resp: Any) -> str:
    """First text block of a response, or '' when there is none."""
    content = getattr(resp, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    return ""


def _invoke_with_retries(
    call: Callable[[], Any], *, max_retries: int, agent_name: str
) -> Any:
    """Run an API call, backing off on transient errors up to ``max_retries``."""
    retryable = _retryable_errors()
    delay = 0.5
    for attempt in range(max_retries + 1):
        try:
            return call()
        except retryable as exc:
            if attempt >= max_retries:
                raise
            log.warning("%s call failed (%s); retry %d/%d in %.1fs",
                        agent_name, type(exc).__name__, attempt + 1, max_retries, delay)
            time.sleep(delay)
            delay *= 2


# ── Result ───────────────────────────────────────────────────


@dataclass
class RuntimeResult:
    """The normalised outcome of one agent call."""

    text: str
    parsed_output: Any | None
    model: str
    stop_reason: str | None
    usage: StepUsage
    autonomy_level: str
    latency_ms: int = 0
    raw: Any = None


# ── The single call site ─────────────────────────────────────


def run_agent(
    agent_name: str,
    *,
    system: str | Sequence[dict[str, Any]],
    messages: list[dict[str, Any]],
    tier: Tier = Tier.CHEAP,
    model: str | None = None,
    output_format: type[BaseModel] | None = None,
    effort: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    cache_system: bool = True,
    cache_ttl_1h: bool = False,
    prompt_version: str | None = None,
    prompt_fragment_ids: Sequence[str] | None = None,
    autonomy_scope: str = "default",
    required_autonomy: str | None = None,
    token_budget: int | None = None,
    max_retries: int = 2,
    input_parts: Sequence[Any] | None = None,
    client: Any | None = None,
) -> RuntimeResult:
    """
    Make one Anthropic call: budgeted, cached, traced, autonomy-checked, retried.

    ``output_format`` routes through ``messages.parse`` for a validated pydantic
    object on ``.parsed_output``; otherwise ``messages.create`` returns text.
    ``required_autonomy`` gates the call itself (most model calls leave it None
    and gate their *actions* via :func:`enforce_autonomy`); the resolved level is
    recorded on the step regardless. Raises ``BudgetError`` when the pre-flight
    token count exceeds ``token_budget``.

    ``model`` overrides the tier's ladder rung. It exists for call sites that
    are mid-migration and must keep sending a model an operator pinned in the
    environment -- ``rag/generator.py`` reads ``LLM_MODEL``, which is set in
    production, so folding it into the runtime without this would silently swap
    the model. Leave it None and the ladder decides, which is the intended
    steady state.
    """
    model = model or model_for_tier(tier)
    autonomy_level = (
        enforce_autonomy(agent_name, required_autonomy, scope=autonomy_scope)
        if required_autonomy
        else resolve_autonomy_level(agent_name, autonomy_scope)
    )
    api = _build_client(client)

    counted = _count_tokens(api, model, system=system, messages=messages)
    if token_budget is not None and counted is not None and counted > token_budget:
        raise BudgetError(
            f"{agent_name} needs {counted} input tokens, budget is {token_budget}"
        )
    caches_ok = counted is not None and counted >= min_cache_prefix(model)
    system_field = _system_payload(
        system, cache=cache_system, cache_ttl_1h=cache_ttl_1h, caches_ok=caches_ok
    )

    started = time.perf_counter()
    try:
        resp = _dispatch(
            api, model=model, system=system_field, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
            output_format=output_format, output_config=_output_config(effort),
            agent_name=agent_name, max_retries=max_retries,
        )
    except Exception as exc:
        record_step(
            agent_name, model=model, autonomy_level=autonomy_level,
            latency_ms=int((time.perf_counter() - started) * 1000),
            prompt_version=prompt_version, status="error",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

    result = _finish(
        resp, agent_name=agent_name, model=model, autonomy_level=autonomy_level,
        started=started, prompt_version=prompt_version,
        prompt_fragment_ids=prompt_fragment_ids, cache_ttl_1h=cache_ttl_1h,
        input_parts=input_parts, output_format=output_format,
    )
    return result


# Models that reject the `temperature` parameter, learned at runtime. The newer
# Claude generation (Sonnet 5, Opus 4.8, ...) deprecated the knob and 400s on it,
# while Haiku 4.5 still accepts it. Rather than hard-code a list that rots as the
# ladder changes, the first rejection for a model is remembered here so every
# later call in the process skips `temperature` for it — one wasted call, once.
_TEMPERATURE_UNSUPPORTED: set[str] = set()


def _is_temperature_deprecated(exc: Exception) -> bool:
    """True when a 400 says the model no longer accepts `temperature`."""
    msg = str(exc).lower()
    return "temperature" in msg and (
        "deprecat" in msg or "not support" in msg or "unsupported" in msg
    )


def _dispatch(
    api: Any,
    *,
    model: str,
    system: Any,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    output_format: type[BaseModel] | None,
    output_config: dict[str, Any] | None,
    agent_name: str,
    max_retries: int,
) -> Any:
    """Route to parse (structured) or create (text), with retries."""

    def _call(include_temperature: bool) -> Any:
        kwargs: dict[str, Any] = {
            "model": model, "max_tokens": max_tokens,
            "system": system, "messages": messages,
        }
        if include_temperature:
            kwargs["temperature"] = temperature
        if output_config is not None:
            kwargs["output_config"] = output_config
        if output_format is not None:
            return _invoke_with_retries(
                lambda: api.messages.parse(output_format=output_format, **kwargs),
                max_retries=max_retries, agent_name=agent_name,
            )
        return _invoke_with_retries(
            lambda: api.messages.create(**kwargs),
            max_retries=max_retries, agent_name=agent_name,
        )

    include_temp = model not in _TEMPERATURE_UNSUPPORTED
    try:
        return _call(include_temp)
    except Exception as exc:
        if include_temp and _is_temperature_deprecated(exc):
            _TEMPERATURE_UNSUPPORTED.add(model)
            log.info("temperature not accepted by %s; retrying without it", model)
            return _call(include_temperature=False)
        raise


def _finish(
    resp: Any,
    *,
    agent_name: str,
    model: str,
    autonomy_level: str,
    started: float,
    prompt_version: str | None,
    prompt_fragment_ids: Sequence[str] | None,
    cache_ttl_1h: bool,
    input_parts: Sequence[Any] | None,
    output_format: type[BaseModel] | None,
) -> RuntimeResult:
    """Trace the successful call and package a RuntimeResult."""
    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = usage_from(resp)
    step_hash = input_hash(*input_parts) if input_parts else None
    record_step(
        agent_name, model=model, usage=usage, latency_ms=latency_ms,
        autonomy_level=autonomy_level, prompt_version=prompt_version,
        prompt_fragment_ids=prompt_fragment_ids,
        step_input_hash=step_hash, cache_ttl_1h=cache_ttl_1h,
    )
    return RuntimeResult(
        text=_extract_text(resp),
        parsed_output=getattr(resp, "parsed_output", None) if output_format else None,
        model=str(getattr(resp, "model", model)),
        stop_reason=getattr(resp, "stop_reason", None),
        usage=usage,
        autonomy_level=autonomy_level,
        latency_ms=latency_ms,
        raw=resp,
    )
