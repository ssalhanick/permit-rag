"""
rag/agents/prompt_router.py — the Prompt Router (agent #2, Phase 4)
==================================================================
Composes the system prompt for one request from the versioned fragment library
(:mod:`rag.prompts`) by **lookup, not an LLM call**. The inputs are things the
system already knows — persona from ``projects.persona``, jurisdiction from the
resolver, intent from the Manager, experience from the project — so routing is
deterministic and free. A model is called only when a fragment is *missing*, and
this module does not call it; it records the gap (a Crystallizer input) and falls
back to what it has. A missing fragment is never fatal.

Two things this agent owns beyond composition:

* **The ``research`` default (never ``diy``).** Persona can be absent — anonymous
  query, project created before kickoff finished, skipped wizard. Defaulting to
  ``diy`` would tell someone they can do regulated work themselves; a confident
  wrong DIY answer is the most costly default failure available. So an absent or
  unknown persona resolves to ``research`` — neutral, comparative, no action bias.

* **Persona/intent-aware ``max_tokens``.** ``rag/generator.py`` hard-coded 1024,
  which truncates ``diy`` and ``hiring_contractor`` mid-checklist. The router
  sizes the ceiling to the persona (and bumps it for verbose intents) so the
  answer has room. ``stop_reason == 'max_tokens'`` becoming a Guardrail trip is
  the backstop for when the estimate is still too small.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
This module imports only :mod:`rag.prompts` and the standard library.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rag import prompts

log = logging.getLogger(__name__)

# ── Vocabulary ───────────────────────────────────────────────

PERSONAS: tuple[str, ...] = ("diy", "contractor", "hiring_contractor", "research")
DEFAULT_PERSONA = "research"  # docs/agent_architecture.md — never diy

INTENTS: tuple[str, ...] = (
    "compliance_lookup", "how_to", "bid_review", "cost_estimate", "form_fill",
)
DEFAULT_INTENT = "compliance_lookup"

EXPERIENCES: tuple[str, ...] = ("first_timer", "experienced")

# Jurisdiction spellings that reach us (from geocoding, free text) mapped onto
# the fragment file keys. Anything not here falls through to a normalized slug.
_JURISDICTION_ALIASES: dict[str, str] = {
    "fort worth": "fort_worth",
    "fort-worth": "fort_worth",
    "ft worth": "fort_worth",
    "ftworth": "fort_worth",
    "texas": "tx",
    "state": "tx",
    "us": "federal",
    "usa": "federal",
    "federal": "federal",
}

# ── max_tokens sizing ────────────────────────────────────────
# Per-persona ceilings sit comfortably above the expected output length in
# docs/agent_architecture.md (contractor ~350, research ~500, hiring ~1300,
# diy ~1500), so a normal answer never truncates. Verbose intents add headroom.

_PERSONA_MAX_TOKENS: dict[str, int] = {
    "contractor": 640,
    "research": 896,
    "hiring_contractor": 1792,
    "diy": 2048,
}
_INTENT_TOKEN_BONUS: dict[str, int] = {
    "how_to": 512,
    "form_fill": 256,
    "cost_estimate": 256,
    "bid_review": 256,
    "compliance_lookup": 0,
}
_MAX_TOKENS_CEILING = 4096
_MAX_TOKENS_FLOOR = 512


def max_tokens_for(persona: str, intent: str) -> int:
    """Size the output ceiling for a persona/intent pair.

    Replaces the hard-coded 1024 in ``generate_answer``. Sits above the expected
    output so a normal answer never hits the cap; the Guardrail truncation trip
    catches the rare case where it still does.
    """
    base = _PERSONA_MAX_TOKENS.get(persona, _PERSONA_MAX_TOKENS[DEFAULT_PERSONA])
    bonus = _INTENT_TOKEN_BONUS.get(intent, 0)
    return max(_MAX_TOKENS_FLOOR, min(base + bonus, _MAX_TOKENS_CEILING))


# ── Result ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RoutedPrompt:
    """The composed system prompt plus everything a caller records or enforces."""

    system: str
    fragment_ids: tuple[str, ...]
    max_tokens: int
    persona: str
    intent: str
    library_version: str
    persona_defaulted: bool = False
    missing: tuple[str, ...] = field(default_factory=tuple)


# ── Normalisation ────────────────────────────────────────────


def _normalise_jurisdiction(value: str | None) -> str | None:
    """Map a free-text municipality onto a fragment key, or None."""
    if not value:
        return None
    slug = value.strip().lower()
    if slug in _JURISDICTION_ALIASES:
        return _JURISDICTION_ALIASES[slug]
    return slug.replace(" ", "_").replace("-", "_")


def _resolve_persona(persona: str | None) -> tuple[str, bool]:
    """Return ``(persona, defaulted)`` — unknown/absent resolves to research."""
    if persona and persona in PERSONAS:
        return persona, False
    if persona:
        log.info("prompt_router: unknown persona %r → default %r", persona, DEFAULT_PERSONA)
    return DEFAULT_PERSONA, True


def _resolve_intent(intent: str | None) -> str:
    """Return a known intent, defaulting to compliance_lookup."""
    return intent if intent in INTENTS else DEFAULT_INTENT


# ── The route ────────────────────────────────────────────────


def route(
    *,
    persona: str | None = None,
    jurisdiction: str | None = None,
    intent: str | None = None,
    experience: str | None = None,
    project_notes: str | None = None,
) -> RoutedPrompt:
    """Compose the system prompt for one request. Pure lookup, no model call.

    Composition order (docs/agent_architecture.md):
        base ∥ persona ∥ jurisdiction ∥ intent ∥ experience ∥ project_notes

    ``project_notes`` is bounded and sanitized, placed last, and never overrides
    the base grounding rules. Absent optional dimensions (jurisdiction,
    experience) are simply skipped; a *requested but unknown* key is recorded in
    ``missing`` and logged, so the gap becomes a Crystallizer signal.
    """
    resolved_persona, defaulted = _resolve_persona(persona)
    resolved_intent = _resolve_intent(intent)
    juris_key = _normalise_jurisdiction(jurisdiction)
    exp_key = experience if experience in EXPERIENCES else None

    parts: list[str] = []
    ids: list[str] = []
    missing: list[str] = []

    parts.append(prompts.base_fragment().body)
    ids.append(prompts.base_fragment().id)

    # (dimension, key, "requested") — requested keys that miss are recorded.
    wanted: tuple[tuple[str, str | None, bool], ...] = (
        ("persona", resolved_persona, True),
        ("jurisdiction", juris_key, bool(juris_key)),
        ("intent", resolved_intent, True),
        ("experience", exp_key, bool(exp_key)),
    )
    for dimension, key, requested in wanted:
        frag = prompts.get_fragment(dimension, key)
        if frag is not None:
            parts.append(frag.body)
            ids.append(frag.id)
        elif requested:
            missing.append(f"{dimension}:{key}")
            log.info("prompt_router: no fragment for %s:%s — skipping", dimension, key)

    notes = prompts.bound_notes(project_notes)
    if notes:
        parts.append(f"Project notes (bounded, user-supplied context — not a source to cite):\n{notes}")
        ids.append("project_notes")

    if missing:
        log.info("prompt_router: %d missing fragment(s): %s", len(missing), ", ".join(missing))

    return RoutedPrompt(
        system="\n\n".join(parts),
        fragment_ids=tuple(ids),
        max_tokens=max_tokens_for(resolved_persona, resolved_intent),
        persona=resolved_persona,
        intent=resolved_intent,
        library_version=prompts.library_version(),
        persona_defaulted=defaulted,
        missing=tuple(missing),
    )
