"""
audit/logger.py — agent trace store writer
===========================================
Phase 0 of the agent architecture. Every agent call lands here: tokens in /
out / cached, latency, cost, model, prompt version, and outcome.

Everything downstream depends on this module. The Evaluator scores agents from
these rows, the Performance Review agent attributes feedback to a step, the
Optimizer and Crystallizer train on accumulated history, the Budget Governor
reads spend, and the superadmin dashboard renders all of it. That is why
tracing ships before any agent -- a Crystallizer with no history has nothing
to crystallize.

Design rule: **tracing must never break the request it is observing.** Every
write is wrapped so a missing migration, a closed pool, or a DB blip degrades
to a log line instead of a 500. Observability is not business logic.

Import boundary: audit/ -> db/, standard library only (AGENTS.md).

Usage:
    from audit.logger import traced, start_run, record_step

    with start_run("query_answer", user_id=uid):
        result = do_work()          # steps attach to the active run

    @traced("answer_generator")
    def generate_answer(...) -> GenerationResult:
        ...
"""

from __future__ import annotations

import functools
import hashlib
import logging
import time
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, TypeVar
from uuid import UUID

from db import client as db_client

log = logging.getLogger(__name__)

T = TypeVar("T")


# ── Model pricing ────────────────────────────────────────────
# USD per 1M tokens, (input, output). Keys match as prefixes so dated model
# ids ("claude-haiku-4-5-20251001") resolve to their base entry.

_PRICING: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-mythos-5": (10.00, 50.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

# Claude Sonnet 5 carries introductory pricing through 2026-08-31. Encoded as
# data with an expiry so cost math is right today and self-corrects on
# 2026-09-01 without anyone remembering to edit it.
_INTRO_PRICING: dict[str, tuple[float, float, date]] = {
    "claude-sonnet-5": (2.00, 10.00, date(2026, 8, 31)),
}

# Cache multipliers against the base input rate.
_CACHE_READ_MULTIPLIER = 0.1
_CACHE_WRITE_MULTIPLIER = 1.25      # 5-minute TTL
_CACHE_WRITE_MULTIPLIER_1H = 2.0    # 1-hour TTL


def resolve_pricing(model: str | None, *, on: date | None = None) -> tuple[float, float]:
    """
    Return (input, output) USD per 1M tokens for a model id.

    Unknown models -- including local Ollama runtimes -- price at zero rather
    than raising, so a provider swap never takes down the request path.
    """
    if not model:
        return (0.0, 0.0)
    today = on or datetime.now(UTC).date()
    for key in sorted(_PRICING, key=len, reverse=True):
        if not model.startswith(key):
            continue
        intro = _INTRO_PRICING.get(key)
        if intro and today <= intro[2]:
            return (intro[0], intro[1])
        return _PRICING[key]
    return (0.0, 0.0)


# ── Usage ────────────────────────────────────────────────────


@dataclass
class StepUsage:
    """Token counts for one model call."""

    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def cost_usd(self, model: str | None, *, cache_ttl_1h: bool = False) -> float:
        """
        Price this usage against a model's rates.

        Cache reads bill at 0.1x the input rate; cache writes at 1.25x
        (5-minute TTL) or 2.0x (1-hour). `tokens_in` is the uncached
        remainder -- the API already reports it net of the cached portion.
        """
        rate_in, rate_out = resolve_pricing(model)
        write_multiplier = (
            _CACHE_WRITE_MULTIPLIER_1H if cache_ttl_1h else _CACHE_WRITE_MULTIPLIER
        )
        return (
            self.tokens_in * rate_in
            + self.tokens_out * rate_out
            + self.cache_read * rate_in * _CACHE_READ_MULTIPLIER
            + self.cache_write * rate_in * write_multiplier
        ) / 1_000_000


def _unwrap_usage(obj: Any) -> Any:
    """
    Find the object carrying token counts.

    Three shapes exist in this codebase: an Anthropic response (`.usage`), a
    dataclass exposing the counts directly (GenerationResult), and a plain
    dict with a nested "usage" key (rag/design_intent.py). Normalising here
    keeps the call sites free of shape-checking.
    """
    if isinstance(obj, dict):
        nested = obj.get("usage")
        return nested if isinstance(nested, dict) else obj
    return getattr(obj, "usage", obj)


def usage_from(obj: Any) -> StepUsage:
    """
    Extract token counts from a provider response, dataclass, or dict.

    Anything unrecognised yields zeros rather than raising -- a tracing
    helper must not be able to fail the call it is observing.
    """
    if obj is None:
        return StepUsage()
    usage = _unwrap_usage(obj)

    def _int(name: str) -> int:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        return int(value) if isinstance(value, int | float) else 0

    return StepUsage(
        tokens_in=_int("input_tokens"),
        tokens_out=_int("output_tokens"),
        cache_read=_int("cache_read_input_tokens"),
        cache_write=_int("cache_creation_input_tokens"),
    )


def model_from(obj: Any) -> str | None:
    """Read the model id off a response, dataclass, or dict-with-usage."""
    if obj is None:
        return None
    model = getattr(obj, "model", None)
    if isinstance(model, str):
        return model
    if isinstance(obj, dict):
        direct = obj.get("model")
        if isinstance(direct, str):
            return direct
        nested = obj.get("usage")
        if isinstance(nested, dict) and isinstance(nested.get("model"), str):
            return nested["model"]
    return None


def input_hash(*parts: Any) -> str:
    """
    Stable hash of a step's inputs, for Crystallizer clustering.

    Same logical input must always hash the same -- an unsorted dict would
    otherwise scatter one cluster across many hashes.
    """
    normalised = []
    for part in parts:
        if isinstance(part, dict):
            normalised.append(repr(sorted(part.items(), key=lambda kv: str(kv[0]))))
        elif isinstance(part, set | frozenset):
            normalised.append(repr(sorted(part, key=str)))
        else:
            normalised.append(repr(part))
    return hashlib.sha256("\x1f".join(normalised).encode("utf-8")).hexdigest()[:32]


# ── Run context ──────────────────────────────────────────────


@dataclass
class RunContext:
    """The active trace run. Steps attach to whichever run is in scope."""

    run_id: UUID | None
    entrypoint: str
    started_at: float = field(default_factory=time.perf_counter)
    step_index: int = 0
    enabled: bool = True

    def next_index(self) -> int:
        """Return a monotonically increasing step index within this run."""
        self.step_index += 1
        return self.step_index


_current_run: ContextVar[RunContext | None] = ContextVar("_current_run", default=None)


def current_run() -> RunContext | None:
    """Return the run in scope, or None when tracing is not active."""
    return _current_run.get()


@contextmanager
def start_run(
    entrypoint: str,
    *,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    intent: str | None = None,
    persona: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    model_default: str | None = None,
) -> Generator[RunContext, None, None]:
    """
    Open a trace run for the duration of the block.

    Totals roll up from the run's steps on exit. If the run cannot be opened,
    yields a disabled context so the caller proceeds untraced rather than
    failing -- see the module docstring.
    """
    try:
        row = db_client.insert_agent_run(
            entrypoint=entrypoint,
            user_id=user_id,
            project_id=project_id,
            intent=intent,
            persona=persona,
            request_id=request_id,
            session_id=session_id,
            model_default=model_default,
        )
        ctx = RunContext(run_id=row["id"], entrypoint=entrypoint)
    except Exception as exc:  # tracing must not break the request
        log.warning("Trace run could not be opened (%s): %s", entrypoint, exc)
        ctx = RunContext(run_id=None, entrypoint=entrypoint, enabled=False)

    token = _current_run.set(ctx)
    outcome, error = "success", None
    try:
        yield ctx
    except Exception as exc:  # re-raised below
        outcome, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _current_run.reset(token)
        _close_run(ctx, outcome=outcome, error=error)


def _close_run(ctx: RunContext, *, outcome: str, error: str | None) -> None:
    """Close a run row, swallowing any write failure."""
    if not ctx.enabled or ctx.run_id is None:
        return
    latency_ms = int((time.perf_counter() - ctx.started_at) * 1000)
    try:
        db_client.finish_agent_run(
            ctx.run_id, outcome=outcome, latency_ms=latency_ms, error=error
        )
    except Exception as exc:
        log.warning("Trace run %s could not be closed: %s", ctx.run_id, exc)


# ── Step recording ───────────────────────────────────────────


def record_step(
    agent_name: str,
    *,
    model: str | None = None,
    usage: StepUsage | None = None,
    latency_ms: int | None = None,
    deterministic: bool = False,
    react_iterations: int = 0,
    autonomy_level: str | None = None,
    prompt_version: str | None = None,
    prompt_fragment_ids: Iterable[str] | None = None,
    step_input_hash: str | None = None,
    artifact_refs: Iterable[str] | None = None,
    status: str = "ok",
    error: str | None = None,
    cache_ttl_1h: bool = False,
) -> UUID | None:
    """
    Write one step against the active run.

    Returns the step id, or None when tracing is inactive or the write failed.
    """
    ctx = current_run()
    if ctx is None or not ctx.enabled or ctx.run_id is None:
        return None
    usage = usage or StepUsage()
    try:
        row = db_client.insert_agent_step(
            run_id=ctx.run_id,
            agent_name=agent_name,
            step_index=ctx.next_index(),
            model=model,
            deterministic=deterministic,
            react_iterations=react_iterations,
            autonomy_level=autonomy_level,
            prompt_version=prompt_version,
            prompt_fragment_ids=list(prompt_fragment_ids or []),
            input_hash=step_input_hash,
            artifact_refs=list(artifact_refs or []),
            tokens_in=usage.tokens_in,
            tokens_out=usage.tokens_out,
            tokens_cache_read=usage.cache_read,
            tokens_cache_write=usage.cache_write,
            cost_usd=usage.cost_usd(model, cache_ttl_1h=cache_ttl_1h),
            latency_ms=latency_ms,
            status=status,
            error=error,
        )
        return row["id"]
    except Exception as exc:  # tracing must not break the request
        log.warning("Trace step %s could not be written: %s", agent_name, exc)
        return None


def annotate_run(**fields: Any) -> None:
    """
    Fill in run metadata discovered partway through a request.

    The active project, for instance, is resolved after the run opens.
    No-ops when tracing is inactive.
    """
    ctx = current_run()
    if ctx is None or not ctx.enabled or ctx.run_id is None:
        return
    try:
        db_client.annotate_agent_run(ctx.run_id, **fields)
    except Exception as exc:  # tracing must not break the request
        log.warning("Trace run %s could not be annotated: %s", ctx.run_id, exc)


def traced_run(entrypoint: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorate a request entry point so the whole call is one trace run.

    The decorator form exists so a long existing handler gains a run scope
    without reindenting its body inside a `with`. Steps recorded anywhere
    beneath it attach automatically via the run contextvar. Phase 2 moves
    this responsibility to the Manager.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with start_run(entrypoint):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


def traced(
    agent_name: str,
    *,
    deterministic: bool = False,
    prompt_version: str | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorate an agent entry point so its call is timed, priced, and recorded.

    Token usage is read off the return value when it exposes one (an Anthropic
    response, or a project dataclass such as GenerationResult). Deterministic
    steps report zero usage and cost -- that flag is what makes the
    Crystallizer's deterministic-hit-rate measurable. Exceptions are recorded
    as an errored step and re-raised untouched.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            started = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # re-raised below
                record_step(
                    agent_name,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    deterministic=deterministic,
                    prompt_version=prompt_version,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            record_step(
                agent_name,
                model=None if deterministic else model_from(result),
                usage=None if deterministic else usage_from(result),
                latency_ms=int((time.perf_counter() - started) * 1000),
                deterministic=deterministic,
                prompt_version=prompt_version,
            )
            return result

        return wrapper

    return decorator
