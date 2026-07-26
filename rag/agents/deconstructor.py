"""
rag/agents/deconstructor.py — Query Deconstructor (agent #5)
===========================================================
Phase 5 answer-path agent. A compound question — "What are the setback and height
limits for a garage in Plano, and do I need an electrical permit?" — retrieves
badly as one embedding: the vector is an average of three unrelated intents. The
Deconstructor splits it into sub-questions, each with its own optional filters
(municipality, permit type), so the Manager can **fan out one retrieval per
sub-question** (the arch's single biggest retrieval win) and merge the results.

**Single-shot structured extraction, deterministic gate first** (arch): a simple
question is by far the common case and needs no model — a query with no
conjunction and one topic is returned as a single sub-question for $0. Only a
query that *looks* compound pays for one ``messages.parse`` call.

Never raises: on any model failure it degrades to the single-question form (the
un-deconstructed query still retrieves, just without fan-out). Import boundary:
rag/agents/ → rag/, db/, audit/, standard library. Model calls via ``run_agent``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from rag.agent_runtime import Tier, run_agent

log = logging.getLogger(__name__)

AGENT_NAME = "query_deconstructor"

# Cheap signals that a query might carry more than one intent. None of these
# *prove* it's compound — they only decide whether the model is worth calling.
_COMPOUND_RE = re.compile(
    r"\b(and|also|as well as|plus|in addition|both)\b|[;&]|\?.*\?",
    re.IGNORECASE,
)


class SubQuestion(BaseModel):
    """One atomic sub-question with the filters it should retrieve under."""

    text: str = Field(description="A single-intent question, self-contained.")
    municipality: str | None = Field(
        default=None, description="Jurisdiction for this sub-question, if named."
    )
    permit_type: str | None = Field(
        default=None, description="Permit type this sub-question is about, if clear."
    )


class Deconstruction(BaseModel):
    """The Deconstructor's output — one or more sub-questions."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)

    @property
    def is_compound(self) -> bool:
        """True when the query split into more than one sub-question."""
        return len(self.sub_questions) > 1


def _looks_compound(query: str) -> bool:
    """Cheap heuristic: is this query worth a deconstruction call?"""
    return bool(_COMPOUND_RE.search(query or ""))


def _single(query: str) -> Deconstruction:
    """Wrap a query as its own sole sub-question (the deterministic path)."""
    return Deconstruction(sub_questions=[SubQuestion(text=(query or "").strip())])


_SYSTEM = (
    "Split the user's permit/compliance question into atomic sub-questions, each "
    "with exactly one intent. For each, fill municipality and permit_type only "
    "when the text makes them unambiguous; otherwise leave them null. If the "
    "question is already atomic, return it unchanged as a single sub-question. "
    "Do not invent sub-questions the user did not ask."
)


def deconstruct(
    query: str,
    *,
    use_llm: bool = True,
    client: Any | None = None,
) -> Deconstruction:
    """Split a compound query into filtered sub-questions; single-shot, gated.

    Returns the single-question form for a simple query (no model call) and on
    any failure. A compound-looking query pays for one structured call.
    """
    text = (query or "").strip()
    if not text:
        return Deconstruction(sub_questions=[])
    if not use_llm or not _looks_compound(text):
        return _single(text)
    try:
        result = run_agent(
            AGENT_NAME,
            system=_SYSTEM,
            messages=[{"role": "user", "content": text}],
            tier=Tier.CHEAP,  # extraction/classification is a haiku task (arch ladder)
            output_format=Deconstruction,
            effort="low",
            max_tokens=512,
            temperature=0.0,
            input_parts=(text,),
            client=client,
        )
    except Exception as exc:  # deconstruction is an optimisation, never a blocker
        log.warning("deconstruction failed, using single-question form: %s", exc)
        return _single(text)
    parsed = result.parsed_output
    # A model that returned nothing (or dropped the query) degrades to single.
    if not parsed.sub_questions:
        return _single(text)
    return parsed
