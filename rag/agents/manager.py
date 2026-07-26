"""
rag/agents/manager.py — the Manager (agent #1)
===============================================
Phase 2 of the agent architecture. Intent routing, plan build, delegation, and
result assembly for the ``/query/answer`` path. This is the hand-wired chain in
``api/routes/query.py`` lifted behind one orchestrator, with **zero behaviour
change** — same inputs, same outputs, same order, same failure modes.

That constraint is the point of the phase, not a courtesy. Introduce the Manager
*and* new answer agents together and a faithfulness delta is unattributable. So
this module adds no capability: it routes to exactly the agents that already
existed, and ``tests/test_query_answer_route.py`` must stay green with no edits
to what it asserts.

**The Manager never sees raw text.** Every step's output goes into an
:class:`~rag.agents.artifacts.ArtifactStore`; the loop carries
:class:`~rag.agents.artifacts.ArtifactRef` ids and summaries only. Payloads are
resolved at the delegation boundary (a step that needs chunks gets them) and at
assembly (the caller reads the answer). That directly bounds ReAct's blast
radius — see the artifacts module docstring.

**The loop is bounded at ``MAX_ITERATIONS = 6``.** The plan is expressed as
ordered waves of steps; the Manager executes a wave, observes the refs it
produced, and decides the next. Today the plan is deterministic and runs in four
waves, well inside the bound; the bound exists so a future replanning Manager
cannot grow the transcript without limit.

**What is injected, and why.** Retrieval and the grounding thresholds are passed
in by the caller rather than imported here. ``api/`` owns those knobs today
(``MIN_GROUNDED_CHUNKS`` / ``MIN_GROUNDED_TOP_SIM`` are read from the route's
environment) and the route is the layer allowed to depend on both sides. Every
other collaborator resolves lazily through
:mod:`rag.agents.registry`, so the roster stays enumerable without importing
each agent's dependencies.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
The Manager must NOT import commerce/, forms/, or bids/; ``api/main.py``
injects agents backed by those packages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from audit.logger import record_step
from rag.agents import registry
from rag.agents.artifacts import ArtifactRef, ArtifactStore
from rag.agents.budget import BudgetGovernor
from rag.agents.guardrail import check_media_sources

log = logging.getLogger(__name__)

# Hard ceiling on Manager ReAct iterations (docs/agent_architecture.md).
MAX_ITERATIONS = 6

# User-facing abstain messages. A grounding-floor miss is a valid *outcome*, not
# an error (Phase 4 query-UX pass): retrieval ran fine, the system simply chose
# not to answer without enough support. These read conversationally so the route
# can return a 200 the frontend renders as an assistant turn, not a red error.
_ABSTAIN_EMPTY = (
    "I couldn't find anything in the code corpus that matches this question. "
    "Try naming a specific city (Dallas, Plano, Frisco, McKinney, or Fort Worth) "
    "or rephrasing with the type of work involved."
)
_ABSTAIN_LOW_CONFIDENCE = (
    "I found some possibly related material, but not enough to answer this "
    "confidently from the code. Try naming a specific city (Dallas, Plano, Frisco, "
    "McKinney, or Fort Worth), or rephrasing to be more specific about the permit "
    "or work type — I'd rather say so than guess on a compliance question."
)


# ── Failure signalling ───────────────────────────────────────


class ManagerError(RuntimeError):
    """
    A plan step failed in a way the caller must surface to the user.

    ``stage`` and ``kind`` let the HTTP layer reproduce today's exact status
    codes without the Manager importing fastapi: retrieval/failure and
    generation/* are 500s, grounding/* are 422s.
    """

    def __init__(self, message: str, *, stage: str, kind: str) -> None:
        """Record which plan stage failed and how."""
        super().__init__(message)
        self.stage = stage
        self.kind = kind


class StepObserver(Protocol):
    """
    Optional per-stage callbacks, so a caller can span the plan.

    ``api/routes/query.py`` implements this over its LangSmith helpers, keeping
    the existing ``api_retrieval`` / ``api_generation`` spans byte-identical
    while the orchestration itself moves in here.
    """

    def started(self, stage: str, inputs: dict[str, Any]) -> None:
        """A stage is about to run."""

    def finished(self, stage: str, outputs: dict[str, Any]) -> None:
        """A stage completed."""

    def failed(self, stage: str, error: str) -> None:
        """A stage raised."""


# ── Request / dependencies / result ──────────────────────────


@dataclass
class ManagerRequest:
    """One user-facing question plus the retrieval knobs that shape it."""

    query: str
    top_k: int = 5
    municipality: str | None = None
    address: str | None = None
    min_similarity: float = 0.0
    project_id: str | None = None
    chunk_ids: list[str] | None = None


@dataclass
class ManagerDeps:
    """
    Collaborators the caller owns.

    ``retrieve`` is injected rather than imported because the route is where the
    retrieval entry point is configured (and patched). ``min_chunks`` and
    ``min_top_sim`` are the grounding guard's thresholds, read from the caller's
    environment at call time.
    """

    retrieve: Callable[..., Any]
    min_chunks: int = 3
    min_top_sim: float = 0.74
    observer: StepObserver | None = None
    governor: BudgetGovernor | None = None
    # Media Curator Slice C2 — the DIY how-to fallback. When a diy query abstains
    # on compliance, retrieve over how-to transcripts instead. Injected like
    # ``retrieve``; None disables the fallback (the query stays a plain abstain).
    # The how-to grounding floor is deliberately looser than compliance — transcript
    # prose sits lower on cosine similarity than statute text.
    retrieve_how_to: Callable[..., Any] | None = None
    how_to_min_chunks: int = 1
    how_to_min_top_sim: float = 0.50


@dataclass
class ManagerResult:
    """
    The assembled outcome. Payloads are resolved from the store, not carried.

    The Manager's loop only ever held the refs in ``artifacts``; these accessors
    exist for the caller, which does need the real objects to build a response.
    """

    store: ArtifactStore
    artifacts: list[ArtifactRef]
    retrieval_ref: ArtifactRef
    generation_ref: ArtifactRef | None = None
    permit_types: list[str] = field(default_factory=list)
    resolved_municipality: str | None = None
    effective_municipality: str | None = None
    conflict_warnings: list[dict[str, Any]] = field(default_factory=list)
    project_context: dict[str, Any] | None = None
    iterations: int = 0
    persona_defaulted: bool = False
    # Phase 4 query-UX: a grounding-floor miss is a soft abstain, not a raise.
    # When True, ``generation_ref`` is None and ``abstain_message`` is the
    # user-facing text; the route returns it as a 200, not a 422.
    abstained: bool = False
    abstain_message: str | None = None
    # Phase 4 second pass: sourced how-to videos for the diy path. Empty for every
    # other persona, on an abstain, and when the query names no curated task.
    media_refs: list[Any] = field(default_factory=list)
    # Media C2: True when this answer was generated from how-to transcripts (a diy
    # compliance-abstain grounded on video content). The route attaches the
    # educational disclaimer and the frontend labels it accordingly.
    how_to: bool = False
    # Citation Verifier (#9): sentences citing a chunk retrieval never returned
    # (fabricated citations). Empty on a clean answer and on an abstain.
    unsupported_citations: list[str] = field(default_factory=list)

    @property
    def retrieval(self) -> Any:
        """The ``RetrievalResult`` produced by the retrieval wave."""
        return self.store.get(self.retrieval_ref)

    @property
    def generation(self) -> Any:
        """The ``GenerationResult`` produced by the generation wave (None if abstained)."""
        return self.store.get_or_none(self.generation_ref)


# ── Plan state ───────────────────────────────────────────────


@dataclass
class _PlanState:
    """Mutable state threaded through the waves. Refs only, never payloads."""

    request: ManagerRequest
    deps: ManagerDeps
    store: ArtifactStore
    governor: BudgetGovernor
    permit_types: list[str] = field(default_factory=list)
    resolved_municipality: str | None = None
    effective_municipality: str | None = None
    conflict_warnings: list[dict[str, Any]] = field(default_factory=list)
    project_context_ref: ArtifactRef | None = None
    retrieval_ref: ArtifactRef | None = None
    generation_ref: ArtifactRef | None = None
    persona_defaulted: bool = False
    abstained: bool = False
    abstain_message: str | None = None
    # Set by _route_prompt so the media curator can read the resolved persona
    # (unknown/absent → research → no videos) without re-routing.
    resolved_persona: str | None = None
    routed: Any = None  # the RoutedPrompt (or None on router failure); reused by C2
    how_to_result: Any = None  # cached how-to retrieval, shared by links + answer
    # Query Deconstructor (#5): sub-questions for retrieval fan-out. A single
    # entry (or empty) means a simple query — retrieval takes the unchanged path.
    sub_questions: list[Any] = field(default_factory=list)
    # The chunks the answer was generated over (compliance or how-to), so the
    # Citation Verifier resolves citations against the exact set the model saw.
    answer_chunks: list[dict[str, Any]] = field(default_factory=list)
    citation_report: Any = None  # Citation Verifier (#9) output; None until wave 5
    media_refs: list[Any] = field(default_factory=list)
    # Media C2: True when a diy compliance-abstain was answered from how-to
    # transcripts instead. The answer is grounded in video content, not code.
    how_to: bool = False


def _agent(name: str) -> Callable[..., Any]:
    """
    Resolve a registered agent's callable.

    Going through the registry rather than importing is what makes the roster
    swappable: ``api/main.py`` can replace a spec at startup and the Manager
    follows without edits.
    """
    return registry.get(name).callable


# ── Wave 1 — pre-retrieval, independent, deterministic ───────


def _classify_permit_types(state: _PlanState) -> None:
    """Classify permit types. Non-blocking: a failure degrades to []."""
    try:
        state.permit_types = _agent("permit_classifier")(state.request.query)
        log.info("permit_types detected: %s", state.permit_types)
    except Exception as exc:
        log.warning("permit_classifier failed (%s) — defaulting to []", exc)
        state.permit_types = []


def _resolve_municipality(state: _PlanState) -> None:
    """Resolve the effective municipality for retrieval + routing. Non-blocking.

    Precedence: an explicit request municipality → the project's stored
    municipality (kickoff) → geocoding an address (request or project). Project
    context is loaded earlier in the plan (wave 1) so a project-scoped query is
    jurisdiction-aware even when the client sends only a project_id.
    """
    request = state.request
    state.effective_municipality = request.municipality
    if request.municipality:
        return

    ctx = state.store.get_or_none(state.project_context_ref) or {}
    # A project can carry an explicit municipality (set at kickoff) — use it as-is.
    if ctx.get("municipality"):
        state.effective_municipality = ctx["municipality"]
        return

    address = request.address or ctx.get("address")
    if not address:
        return
    try:
        resolved = _agent("jurisdiction_resolver")(address)
        if resolved:
            state.resolved_municipality = resolved
            state.effective_municipality = resolved
            log.info("address geocoded to municipality='%s' for address=%r", resolved, address)
        else:
            log.info("address geocoding returned no match for %r", address)
    except Exception as exc:
        log.warning("jurisdiction_resolver failed (%s) — skipping auto-municipality", exc)


# ── Wave 2 — retrieval and the grounding guard ───────────────


def _retrieve_by_ids(state: _PlanState) -> Any:
    """Build a RetrievalResult from explicit chunk ids, bypassing search."""
    from uuid import UUID

    from db.client import get_chunks_by_ids
    from rag.retriever import RetrievalResult

    ids = [UUID(cid) for cid in (state.request.chunk_ids or [])]
    return RetrievalResult(
        query=state.request.query,
        chunks=get_chunks_by_ids(ids),
        top_k=state.request.top_k,
        municipality=state.effective_municipality,
        latency_ms=0,
    )


def _deconstruct(state: _PlanState) -> None:
    """Split a compound query into sub-questions (Query Deconstructor #5).

    Runs pre-retrieval. The deconstructor gates itself: a simple query returns a
    single sub-question with no model call, so retrieval stays on the unchanged
    path. Explicit chunk-id requests skip deconstruction entirely. Never fatal —
    a failure leaves ``sub_questions`` empty (the single-question path).
    """
    if state.request.chunk_ids:
        return
    try:
        result = _agent("query_deconstructor")(state.request.query)
        state.sub_questions = list(result.sub_questions)
    except Exception as exc:  # deconstruction is an optimisation, never a blocker
        log.warning("deconstruction failed (%s) — single-question retrieval", exc)
        state.sub_questions = []


def _single_retrieval(state: _PlanState) -> Any:
    """Today's retrieval: one search on the original query. Behaviour-unchanged."""
    r = state.request
    return state.deps.retrieve(
        r.query,
        project_id=r.project_id,
        top_k=r.top_k,
        municipality=state.effective_municipality,
        min_similarity=r.min_similarity,
    )


def _fanout_retrieval(state: _PlanState) -> Any:
    """One retrieval per sub-question, merged into a single RetrievalResult.

    Each sub-question retrieves under its own filters (its named municipality, or
    the project's); the union is deduped by chunk id and re-ranked, so the final
    top-k is drawn from a better pool than a single averaged-embedding search of
    the compound question. Capped at ``top_k`` so generation context and grounding
    behave exactly as today. Returns None to fall back to single retrieval when no
    sub-question returned anything.
    """
    from rag.retriever import RetrievalResult

    r = state.request
    merged: list[dict[str, Any]] = []
    seen: set[Any] = set()
    latency = 0
    for sub in state.sub_questions:
        muni = getattr(sub, "municipality", None) or state.effective_municipality
        try:
            res = state.deps.retrieve(
                sub.text, project_id=r.project_id, top_k=r.top_k,
                municipality=muni, min_similarity=r.min_similarity,
            )
        except Exception as exc:  # one weak sub-question must not fail the whole query
            log.warning("sub-question retrieval failed (%s)", exc)
            continue
        latency += int(getattr(res, "latency_ms", 0) or 0)
        for c in res.chunks:
            cid = c.get("id")
            if cid not in seen:
                seen.add(cid)
                merged.append(c)
    if not merged:
        return None
    merged.sort(key=lambda c: c.get("reranked_score") or c.get("similarity") or 0.0, reverse=True)
    return RetrievalResult(
        query=r.query, chunks=merged[: r.top_k], top_k=r.top_k,
        municipality=state.effective_municipality, latency_ms=latency,
    )


def _run_retrieval(state: _PlanState) -> None:
    """Retrieve, store the result as an artifact, and span it for the observer."""
    request, deps = state.request, state.deps
    _notify(deps, "started", "retrieval", {
        "query": request.query,
        "municipality": state.effective_municipality,
        "top_k": request.top_k,
    })
    try:
        if request.chunk_ids:
            result = _retrieve_by_ids(state)
        elif len(state.sub_questions) > 1:
            # Compound query: fan out, falling back to the single path on an empty union.
            result = _fanout_retrieval(state) or _single_retrieval(state)
        else:
            result = _single_retrieval(state)
    except Exception as exc:
        log.exception("Retrieval failed for query: %s", request.query)
        _notify(deps, "failed", "retrieval", f"Retrieval error: {exc}")
        raise ManagerError(
            f"Retrieval error: {exc}", stage="retrieval", kind="failure"
        ) from exc

    state.retrieval_ref = state.store.put(
        "chunks", result, summary=_summarise_retrieval(result)
    )
    _notify(deps, "finished", "retrieval", {
        "num_results": result.num_results,
        "top_similarity": result.top_similarity,
        "latency_retrieval_ms": result.latency_ms,
        "unique_doc_ids": result.unique_documents,
    })


def _check_grounding(state: _PlanState) -> None:
    """
    Enforce the grounding floor as a soft **abstain**, not an exception.

    A grounding-floor miss is a valid outcome — retrieval ran; the system chose
    not to answer without support. Phase 4's query-UX pass turned this from a
    ``ManagerError`` (→ 422 red error) into an abstain the route returns as a 200
    the frontend renders conversationally. ``_generate`` skips generation when
    ``state.abstained`` is set. The diagnostic numbers still reach the caller via
    the retrieval result's ``diagnostics``; only the user-facing text is friendly.

    Genuine retrieval and generation *failures* still raise ``ManagerError`` (500).
    """
    result = state.store.get(state.retrieval_ref)
    if not result.chunks:
        state.abstained = True
        state.abstain_message = _ABSTAIN_EMPTY
        log.info("grounding abstain: no chunks retrieved for %r", state.request.query)
        return
    deps = state.deps
    if result.num_results >= deps.min_chunks and result.top_similarity >= deps.min_top_sim:
        return
    state.abstained = True
    state.abstain_message = _ABSTAIN_LOW_CONFIDENCE
    log.info(
        "grounding abstain: chunks=%d top_sim=%.4f (need >=%d / >=%.2f) for %r",
        result.num_results, result.top_similarity, deps.min_chunks,
        deps.min_top_sim, state.request.query,
    )


# ── Wave 3 — post-retrieval enrichment, all non-blocking ─────


def _detect_conflicts(state: _PlanState) -> None:
    """Lightweight conflict detection over the retrieved chunks. Non-blocking."""
    chunks = state.store.get(state.retrieval_ref).chunks
    try:
        raw = _agent("conflict_detector")(chunks)
        state.conflict_warnings.extend(
            {
                "subject": c.subject,
                "chunk_a_doc_id": c.chunk_a.get("doc_id", ""),
                "chunk_a_index": int(c.chunk_a.get("chunk_index", 0)),
                "chunk_a_authority": str(c.chunk_a.get("authority_level", "")),
                "chunk_b_doc_id": c.chunk_b.get("doc_id", ""),
                "chunk_b_index": int(c.chunk_b.get("chunk_index", 0)),
                "chunk_b_authority": str(c.chunk_b.get("authority_level", "")),
                "detail": c.detail,
            }
            for c in raw
        )
        if state.conflict_warnings:
            log.info(
                "conflict_warnings: %d conflict(s) detected", len(state.conflict_warnings)
            )
    except Exception as exc:
        log.warning("conflict_detector failed (%s) — skipping", exc)


def _detect_upload_conflicts(state: _PlanState) -> None:
    """Compare corpus chunks against project uploads. Non-blocking, project-only."""
    if not state.request.project_id:
        return
    chunks = state.store.get(state.retrieval_ref).chunks
    try:
        corpus = [c for c in chunks if int(c.get("source_tier", 1)) == 1]
        project = [c for c in chunks if int(c.get("source_tier", 1)) >= 2]
        for warn in _agent("mini_rag_conflicts")(corpus, project):
            state.conflict_warnings.append(
                {"subject": warn["subject"], "detail": warn["detail"],
                 **_side("chunk_a", corpus), **_side("chunk_b", project)}
            )
    except Exception as exc:
        log.warning("mini_rag conflict check failed (%s)", exc)


def _side(prefix: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe one side of an upload conflict from its first chunk."""
    head = chunks[0] if chunks else {}
    return {
        f"{prefix}_doc_id": head.get("doc_id", ""),
        f"{prefix}_index": int(head.get("chunk_index", 0)),
        f"{prefix}_authority": str(head.get("authority_level", "")),
    }


def _load_project_context(state: _PlanState) -> None:
    """Load kickoff + room-derived project facts. Non-blocking, project-only."""
    if not state.request.project_id:
        return
    try:
        context = _agent("project_context")(state.request.project_id)
    except Exception as exc:
        log.warning("project_context load failed (%s)", exc)
        return
    if context is not None:
        state.project_context_ref = state.store.put(
            "project_context", context, summary=_summarise_context(context)
        )


# ── Wave 4 — prompt routing + generation ─────────────────────


def _derive_intent(query: str) -> str:
    """Deterministically pick an intent fragment from the query. No model call.

    A cheap heuristic, not a classifier — the Prompt Router treats an unknown
    intent as compliance_lookup anyway, so a miss here degrades safely. A learned
    intent (from the Manager/Deconstructor) can replace this later.
    """
    q = query.lower()
    if any(k in q for k in ("how do i", "how to", "how can i", "steps to", "install")):
        return "how_to"
    if any(k in q for k in ("cost", "fee", "how much", "price", "estimate")):
        return "cost_estimate"
    if "bid" in q:
        return "bid_review"
    return "compliance_lookup"


def _route_prompt(state: _PlanState) -> Any:
    """Compose the system prompt via the Prompt Router (Phase 4). Deterministic.

    Reads persona/experience/notes from the loaded project context and the
    jurisdiction the plan already resolved; returns a ``RoutedPrompt`` or None.
    A router failure degrades to the legacy (un-routed) prompt rather than
    failing the query — composition must never be the reason an answer 500s.
    """
    ctx = state.store.get_or_none(state.project_context_ref) or {}
    log.info(
        "route: project_id=%s context_loaded=%s persona=%r municipality=%r",
        state.request.project_id, state.project_context_ref is not None,
        ctx.get("persona"), state.effective_municipality,
    )
    try:
        routed = _agent("prompt_router")(
            persona=ctx.get("persona"),
            jurisdiction=state.effective_municipality,
            intent=_derive_intent(state.request.query),
            experience=ctx.get("experience"),
            project_notes=ctx.get("project_notes") or ctx.get("custom_system_prompt"),
        )
    except Exception as exc:
        log.warning("prompt_router failed (%s) — falling back to legacy prompt", exc)
        return None
    state.persona_defaulted = routed.persona_defaulted
    state.resolved_persona = routed.persona
    state.routed = routed
    # A deterministic step of its own, so fragment ids are attributable at
    # router grain too — not only on the generator step.
    record_step(
        "prompt_router",
        deterministic=True,
        prompt_version=routed.library_version,
        prompt_fragment_ids=list(routed.fragment_ids),
        status="ok",
    )
    return routed


def _guard_truncation(state: _PlanState, gen: Any) -> None:
    """Fire the Guardrail truncation trip. Never blocks the answer."""
    try:
        _agent("guardrail")(
            gen, query=state.request.query, entity_id=state.request.project_id or None
        )
    except Exception as exc:  # guardrail is best-effort; never fatal
        log.warning("guardrail truncation check failed (%s)", exc)


def _generate(state: _PlanState) -> None:
    """
    Route the prompt, then delegate to the answer generator over the
    reranker-passing chunks only.

    Rejected chunks must not be prompted or billed (Phase 0, defect #2); the
    generator re-filters defensively for its other callers. The Prompt Router
    (Phase 4) composes the persona-aware system prompt and sizes ``max_tokens``;
    the Guardrail trips when a generation still truncates.
    """
    request, deps = state.request, state.deps
    # A grounding-floor abstain skips generation entirely (no LLM call), but still
    # routes so ``persona_defaulted`` is set — the Clarification nudge should show
    # on an abstain too. No generation_ref is produced; the route returns the
    # abstain message as a 200.
    if state.abstained:
        _route_prompt(state)
        return
    result = state.store.get(state.retrieval_ref)
    chunks, _ = state.governor.degrade(
        "answer_generator", list(result.passing_chunks), overhead_tokens=600
    )
    routed = _route_prompt(state)
    _notify(deps, "started", "generation", {
        "query": request.query,
        "num_chunks": result.num_results,
        "num_chunks_prompted": len(chunks),
    })
    try:
        gen = _agent("answer_generator")(
            request.query, chunks,
            project_context=state.store.get_or_none(state.project_context_ref),
            routed=routed,
        )
    except RuntimeError as exc:  # provider credentials missing
        log.error("Generator config error: %s", exc)
        _notify(deps, "failed", "generation", str(exc))
        raise ManagerError(str(exc), stage="generation", kind="config") from exc
    except Exception as exc:
        log.exception("Generation failed for query: %s", request.query)
        _notify(deps, "failed", "generation", f"Generation error: {exc}")
        raise ManagerError(
            f"Generation error: {exc}", stage="generation", kind="failure"
        ) from exc

    _guard_truncation(state, gen)
    # All retrieved chunks (not just the degraded subset) — every chunk the
    # generator could legitimately cite resolves, so a citation flagged
    # unsupported is a real fabrication, not a budget-degrade artifact.
    state.answer_chunks = result.chunks
    state.generation_ref = state.store.put(
        "answer", gen, summary=_summarise_generation(gen)
    )
    state.governor.charge(
        int(getattr(gen, "input_tokens", 0) or 0), int(getattr(gen, "output_tokens", 0) or 0)
    )
    _notify(deps, "finished", "generation", {
        "model": gen.model,
        "input_tokens": gen.input_tokens,
        "output_tokens": gen.output_tokens,
        "latency_generation_ms": gen.latency_ms,
        "citation_count": len(gen.citations),
    })


def _ensure_how_to_retrieval(state: _PlanState) -> Any:
    """Retrieve over the how-to transcript class once per diy query, cached.

    Shared by the semantic-links path (:func:`_curate_media`) and the how-to
    answer (:func:`_how_to_fallback`) so a diy query embeds + queries transcripts
    at most once. Returns the RetrievalResult, or None when unavailable/not diy.
    Best-effort: a failure caches None and never raises.
    """
    if state.resolved_persona != "diy" or not state.deps.retrieve_how_to:
        return None
    if state.how_to_result is None:
        try:
            state.how_to_result = state.deps.retrieve_how_to(
                state.request.query, top_k=state.request.top_k or 5
            )
        except Exception as exc:  # a media lookup must never break the answer path
            log.warning("how-to retrieval failed (%s)", exc)
            state.how_to_result = None
    return state.how_to_result


def _semantic_media_refs(state: _PlanState) -> list[Any]:
    """Videos behind the semantically-retrieved how-to transcripts.

    Any ingested/crawled video surfaces as a link from a semantic transcript hit,
    with **no hand-assigned task_key** — the scaling unlock for channel ingest.
    Distinct videos in similarity order.
    """
    result = _ensure_how_to_retrieval(state)
    if result is None or not getattr(result, "chunks", None):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for c in result.chunks:
        did = c.get("doc_id")
        if did and did not in seen:
            seen.add(did)
            ordered.append(did)
    try:
        from db.client import fetch_media_refs_for_how_to_docs
        from rag.agents.media import refs_from_rows
        by_doc = {r["doc_id"]: r for r in fetch_media_refs_for_how_to_docs(ordered)}
    except Exception as exc:
        log.warning("semantic media lookup failed (%s)", exc)
        return []
    return refs_from_rows([by_doc[d] for d in ordered if d in by_doc])


def _dedupe_media(refs: list[Any]) -> list[Any]:
    """Distinct media refs by URL, preserving order (task_key first, then semantic)."""
    seen: set[str] = set()
    out: list[Any] = []
    for r in refs:
        url = getattr(r, "url", None)
        if url and url not in seen:
            seen.add(url)
            out.append(r)
    return out


def _curate_media(state: _PlanState) -> None:
    """Attach sourced how-to videos on the diy path (Media Curator, agent #17).

    Two merged sources: the curated ``task_key`` map (fast, and works even when a
    video's transcript was never ingested — e.g. captions unavailable), and
    **semantic** links (videos behind the retrieved how-to transcripts, so any
    ingested/crawled video surfaces with no hand-assigned task_key). diy-only;
    runs on an abstain too (links are worth showing even with no answer). Deduped
    by URL, then passed through the Guardrail source gate. Best-effort, never fatal.
    """
    if state.resolved_persona != "diy":
        return
    refs: list[Any] = []
    try:  # curated task_key links (a boost / transcript-independent fallback)
        refs.extend(_agent("media_curator")(
            state.request.query,
            persona=state.resolved_persona,
            jurisdiction=state.effective_municipality,
            permit_types=state.permit_types,
        ))
    except Exception as exc:
        log.warning("media curator (task_key) failed (%s)", exc)
    try:  # semantic links from the retrieved transcripts
        refs.extend(_semantic_media_refs(state))
    except Exception as exc:
        log.warning("media curator (semantic) failed (%s)", exc)

    state.media_refs = check_media_sources(
        _dedupe_media(refs), entity_id=state.request.project_id or None
    )


def _how_to_fallback(state: _PlanState) -> None:
    """Answer a diy compliance-abstain from how-to transcripts (Media C2).

    When a diy query falls below the compliance grounding floor, retrieve over the
    segregated how-to class (video transcripts). If that clears the looser how-to
    floor, generate a grounded how-to answer with the diy prompt — replacing the
    abstain. The answer is grounded in **video content, never permit code**; the
    route attaches an educational (not AHJ-compliance) disclaimer. Best-effort:
    any miss or failure leaves the plain abstain (with its curated links) intact.
    """
    deps = state.deps
    if not (state.abstained and state.resolved_persona == "diy" and deps.retrieve_how_to):
        return
    result = _ensure_how_to_retrieval(state)  # cached; shared with the links path
    if result is None:
        return

    if result.num_results < deps.how_to_min_chunks or result.top_similarity < deps.how_to_min_top_sim:
        log.info(
            "how-to fallback below floor (chunks=%d, top_sim=%.3f) — staying abstained",
            result.num_results, result.top_similarity,
        )
        return

    chunks = list(result.passing_chunks)
    try:
        gen = _agent("answer_generator")(
            state.request.query, chunks,
            project_context=state.store.get_or_none(state.project_context_ref),
            routed=state.routed,
        )
    except Exception as exc:  # generation failure here is non-fatal: keep the abstain
        log.warning("how-to generation failed (%s) — staying abstained", exc)
        return

    _guard_truncation(state, gen)
    state.answer_chunks = result.chunks  # how-to transcripts this answer cites
    state.generation_ref = state.store.put("answer", gen, summary=_summarise_generation(gen))
    state.governor.charge(
        int(getattr(gen, "input_tokens", 0) or 0), int(getattr(gen, "output_tokens", 0) or 0)
    )
    # A grounded how-to answer replaces the abstain.
    state.abstained = False
    state.abstain_message = None
    state.how_to = True
    _notify(deps, "finished", "how_to_generation", {
        "model": gen.model, "num_chunks": len(chunks), "top_sim": result.top_similarity,
    })


# ── Wave 5 — post-generation citation verification ───────────


def _verify_citations(state: _PlanState) -> None:
    """Check the answer's citations against the chunks it was generated over.

    Deterministic on the hot path (``use_llm=False`` — token-span match only, $0,
    no added latency): it surfaces the unambiguous failure — a claim citing a
    chunk retrieval never returned (a *fabricated* citation) — which in a
    compliance tool is the most dangerous kind of wrong. The full entailment
    pass (paraphrase judgement) runs offline in the Evaluator, not per query.
    Best-effort: any failure leaves the answer untouched.
    """
    if state.abstained or state.generation_ref is None or not state.answer_chunks:
        return
    gen = state.store.get_or_none(state.generation_ref)
    if gen is None:
        return
    try:
        state.citation_report = _agent("citation_verifier")(
            gen.answer, state.answer_chunks, use_llm=False
        )
        record_step("citation_verifier", deterministic=True, status="ok")
    except Exception as exc:  # verification is advisory; never break the answer
        log.warning("citation verification failed (%s)", exc)


def _unsupported_citations(report: Any) -> list[str]:
    """Sentences whose citation points at a chunk retrieval never returned.

    Only the high-confidence fabrication signal is surfaced to the user — the
    middling paraphrase cases are left to the offline entailment pass so a
    legitimately-grounded answer is never flagged on the hot path.
    """
    if report is None:
        return []
    return [c.sentence for c in report.claims if c.method == "missing_chunk"]


# ── Summaries — what the Manager sees instead of the payload ─


def _summarise_retrieval(result: Any) -> str:
    """
    One line describing a retrieval result, with no chunk text in it.

    Counts the passing chunks off ``chunks`` rather than reading the
    ``passing_chunks`` property: the summary is built before the grounding guard
    runs, so it must survive a degenerate or empty result without raising.
    """
    passing = sum(1 for c in result.chunks if not c.get("filtered_out"))
    return (
        f"{result.num_results} chunks / {len(result.unique_documents)} docs, "
        f"top_sim={result.top_similarity:.4f}, "
        f"{passing} passing the reranker"
    )


def _summarise_generation(gen: Any) -> str:
    """One line describing a generated answer, with no answer text in it."""
    return (
        f"{len(gen.answer)} chars, {len(gen.citations)} citations, "
        f"{gen.input_tokens}+{gen.output_tokens} tokens on {gen.model}"
    )


def _summarise_context(context: dict[str, Any]) -> str:
    """One line describing loaded project facts, with no values in it."""
    keys = sorted(context)[:6] if isinstance(context, dict) else []
    return f"project facts: {', '.join(keys) or 'none'}"


def _notify(deps: ManagerDeps, event: str, stage: str, payload: Any) -> None:
    """Fire an observer callback; an observer failure never breaks the plan."""
    if deps.observer is None:
        return
    try:
        getattr(deps.observer, event)(stage, payload)
    except Exception as exc:
        log.warning("step observer %s/%s failed: %s", event, stage, exc)


# ── The plan ─────────────────────────────────────────────────

# Ordered waves. Steps inside a wave are independent of one another; waves are
# strictly sequential. Four waves today, against MAX_ITERATIONS=6.
_PLAN: tuple[tuple[Callable[[_PlanState], None], ...], ...] = (
    # Project context loads first so retrieval + municipality resolution + routing
    # are all project-aware (jurisdiction, persona) from a project_id alone.
    (_load_project_context, _classify_permit_types, _resolve_municipality, _deconstruct),
    (_run_retrieval, _check_grounding),
    (_detect_conflicts, _detect_upload_conflicts),
    (_generate, _curate_media, _how_to_fallback),
    (_verify_citations,),  # post-generation; reads the settled answer + chunks
)


def run_query_plan(request: ManagerRequest, deps: ManagerDeps) -> ManagerResult:
    """
    Route, plan, delegate, and assemble one ``/query/answer`` request.

    Executes the plan wave by wave, bounded at :data:`MAX_ITERATIONS`. Every
    step's output lands in the artifact store; this function holds refs, not
    payloads, until assembly. Raises :class:`ManagerError` for the three failure
    modes the caller turns into HTTP status codes.
    """
    state = _PlanState(
        request=request,
        deps=deps,
        store=ArtifactStore(),
        governor=deps.governor or BudgetGovernor(),
    )
    iterations = 0
    try:
        for wave in _PLAN:
            if iterations >= MAX_ITERATIONS:
                raise ManagerError(
                    f"Manager exceeded {MAX_ITERATIONS} iterations",
                    stage="plan", kind="failure",
                )
            iterations += 1
            for step in wave:
                step(state)
    except ManagerError:
        _record_manager_step(state, iterations, status="error")
        raise

    _record_manager_step(state, iterations, status="ok")
    return _assemble(state, iterations)


def _record_manager_step(state: _PlanState, iterations: int, *, status: str) -> None:
    """Trace the Manager's own orchestration step. Deterministic — no tokens."""
    record_step(
        "manager",
        deterministic=True,
        react_iterations=iterations,
        artifact_refs=state.store.ref_ids(),
        status=status,
    )


def _assemble(state: _PlanState, iterations: int) -> ManagerResult:
    """Package the plan's artifacts into the caller's result object."""
    # generation_ref is None on an abstain; retrieval always ran.
    assert state.retrieval_ref is not None
    assert state.generation_ref is not None or state.abstained
    return ManagerResult(
        store=state.store,
        artifacts=state.store.refs(),
        retrieval_ref=state.retrieval_ref,
        generation_ref=state.generation_ref,
        permit_types=state.permit_types,
        resolved_municipality=state.resolved_municipality,
        effective_municipality=state.effective_municipality,
        conflict_warnings=state.conflict_warnings,
        project_context=state.store.get_or_none(state.project_context_ref),
        iterations=iterations,
        persona_defaulted=state.persona_defaulted,
        abstained=state.abstained,
        abstain_message=state.abstain_message,
        media_refs=state.media_refs,
        how_to=state.how_to,
        unsupported_citations=_unsupported_citations(state.citation_report),
    )
