"""
rag/agents/media.py — the Media Curator (agent #17, Phase 4 second pass)
========================================================================
Sourced how-to video links for the **DIY** answer path. The Curator **never
emits a URL from model memory** — a model-recalled YouTube link is usually dead.
It has two sourced paths (docs/agent_architecture.md #17):

1. the curated ``media_refs`` table — a deterministic lookup, no LLM, $0 (this
   slice, B1);
2. a ``web_search`` pinned to ``allowed_domains:["youtube.com"]`` (a later slice,
   B2, which needs the runtime to learn ``tools=``).

Either way the results pass the **Guardrail** source gate
(``rag.agents.guardrail.check_media_sources``), which drops anything not from a
vetted source — that is the "zero unsourced URLs" hard gate. On this B1 path the
gate never drops a row (every ``media_refs`` row is vetted); it matters once
web_search can propose model-emitted URLs.

The Curator runs **in parallel with the Answer Generator** on the diy path: the
video lookup does not depend on the prose. It is read-only and inline in the
request — no autonomy gate, no side effects.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
``db/`` is allowed, so the Curator reads ``media_refs`` directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

DIY_PERSONA = "diy"

# Task-key vocabulary. The Curator derives a task_key from the query (a keyword
# lookup — the crystallized rule table an LLM task-extractor would replace in B2),
# and ``media_refs.task_key`` is seeded to match these keys. Order matters: the
# first matching phrase wins, so list more specific phrases before generic ones.
_TASK_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("gfci", "ground fault"), "install_gfci_outlet"),
    (("3-way switch", "3 way switch", "three-way switch", "three way switch"),
     "find-correct-wiring-for-3-way-switch"),
    (("outlet", "receptacle"), "install_electrical_outlet"),
    (("ceiling fan",), "install_ceiling_fan"),
    (("light fixture", "light fitting"), "replace_light_fixture"),
    (("water heater",), "replace_water_heater"),
    (("garbage disposal",), "install_garbage_disposal"),
    (("faucet", "sink"), "replace_faucet"),
    (("toilet",), "install_toilet"),
    (("vanity",), "install_vanity"),
    (("drywall", "sheetrock"), "hang_drywall"),
    (("tile", "backsplash"), "lay_tile"),
    (("deck",), "build_deck"),
    (("fence",), "build_fence"),
    (("water softener",), "install_water_softener"),
)


@dataclass(frozen=True)
class MediaRef:
    """One vetted how-to video link surfaced to the user.

    ``sourced`` is always True for a Curator-produced ref (it came from the
    ``media_refs`` table or an allowed-domain search), which is what the Guardrail
    source gate checks. It is a field so the gate can treat a Curator ref and a
    raw dict uniformly.
    """

    title: str
    url: str
    provider: str = "youtube"
    jurisdiction: str | None = None
    relevance_note: str | None = None
    task_key: str | None = None
    sourced: bool = field(default=True)


def _derive_task_key(query: str, permit_types: list[str] | None) -> str | None:
    """Map a query to a media task_key by keyword, or None when nothing matches.

    Deterministic and cheap — a first-match keyword scan over
    :data:`_TASK_KEYWORDS`. Returns None when the query names no task we have
    curated videos for, in which case the Curator surfaces nothing rather than a
    guess. ``permit_types`` is accepted for a future fallback but unused today;
    query text is the reliable signal.
    """
    text = (query or "").lower()
    for phrases, task_key in _TASK_KEYWORDS:
        if any(p in text for p in phrases):
            return task_key
    return None


def curate(
    query: str,
    *,
    persona: str | None,
    jurisdiction: str | None = None,
    permit_types: list[str] | None = None,
    limit: int = 3,
) -> list[MediaRef]:
    """Return vetted how-to videos for a DIY query, or an empty list.

    Non-diy personas get nothing (a contractor does not want a how-to reel; a
    hiring_contractor is explicitly told what *not* to DIY). A query naming no
    curated task gets nothing. Every returned ref is sourced from the
    ``media_refs`` table — the Curator never fabricates a URL.

    Args:
        query: The user question.
        persona: The resolved persona. Only ``diy`` produces videos.
        jurisdiction: Municipality to prefer (national how-tos still apply).
        permit_types: Classified permit types (reserved; query text drives today).
        limit: Max videos to return.
    """
    if persona != DIY_PERSONA:
        return []
    task_key = _derive_task_key(query, permit_types)
    if task_key is None:
        log.debug("media_curator: no curated task for query %r", query)
        return []

    try:
        from db.client import fetch_media_refs

        rows = fetch_media_refs(task_key, jurisdiction=jurisdiction, limit=limit)
    except Exception as exc:  # a media lookup must never break the answer path
        log.warning("media_curator: media_refs lookup failed (%s)", exc)
        return []

    return [_row_to_ref(row) for row in rows]


def _row_to_ref(row: dict) -> MediaRef:
    """Map a ``media_refs`` row dict to a :class:`MediaRef`."""
    return MediaRef(
        title=row["title"],
        url=row["url"],
        provider=row.get("provider", "youtube"),
        jurisdiction=row.get("jurisdiction"),
        relevance_note=row.get("relevance_note"),
        task_key=row.get("task_key"),
        sourced=True,
    )
