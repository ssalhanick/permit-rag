"""
rag/agents/guardrail.py — the Guardrail (agent #4, Phase 4 slice)
================================================================
The Guardrail is the enforcement tier: grounding floor, PII, injection defense,
no-auto-submit, disclaimer presence. It is a *blocker*, not a proposer, and runs
at autonomy L3 by design — a human approving each guard check would defeat it.

This Phase 4 slice adds one check: **answer truncation**. ``max_tokens`` becoming
persona/intent-aware (the Prompt Router) shrinks the chance of a cut-off answer,
but does not eliminate it — an unusually long ``diy`` checklist can still hit the
ceiling. A compliance answer truncated mid-red-flag-list is a bad, near-invisible
failure: it reads as a quality regression when it is a sizing miss. So when the
model reports ``stop_reason == 'max_tokens'`` the Guardrail files a
``agent_action_item`` for a human, and the anomaly detector can watch the rate.

Other Guardrail checks (grounding floor, disclaimer, injection) already live in
``api/routes/query.py`` and ``rag/agents/manager.py``; they migrate under this
module in a later phase. This slice only adds the truncation trip so the Router's
``max_tokens`` change ships with its backstop.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
``db/`` is allowed, so the Guardrail files its own action item directly.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)

TRUNCATION_KIND = "answer_truncated"
SOURCE_AGENT = "guardrail"


def check_truncation(
    gen: Any,
    *,
    query: str | None = None,
    entity_id: str | None = None,
    run_id: UUID | None = None,
) -> bool:
    """File an action item when a generated answer was cut off by ``max_tokens``.

    Returns True when the trip fired. Never raises: a guardrail that can crash the
    answer path is worse than the truncation it guards. The action item is deduped
    on the open-item unique index (``upsert_action_item``), so a repeatedly
    truncating query refreshes one row rather than piling up duplicates.

    Args:
        gen: The generation result. Only ``stop_reason`` and, if present,
            ``output_tokens``/``model`` are read — so a mock or any object with a
            ``stop_reason`` attribute works.
        query: The user query, recorded as evidence.
        entity_id: Stable id for dedupe (a project id, or a query hash). Falls
            back to the query text so distinct queries file distinct items.
        run_id: The trace run id, linking the item to its run when available.
    """
    if getattr(gen, "stop_reason", None) != "max_tokens":
        return False

    try:
        from db.client import upsert_action_item

        upsert_action_item(
            source_agent=SOURCE_AGENT,
            kind=TRUNCATION_KIND,
            title="Answer truncated at max_tokens — output ceiling too low",
            severity="medium",
            blocking=False,
            run_id=run_id,
            entity_type="query",
            entity_id=entity_id or (query or "")[:200],
            evidence={
                "query": query,
                "model": getattr(gen, "model", None),
                "output_tokens": getattr(gen, "output_tokens", None),
                "stop_reason": "max_tokens",
            },
            proposed_action=(
                "Raise the persona/intent max_tokens for this case in "
                "rag/agents/prompt_router.py, or split the question."
            ),
        )
        log.warning(
            "guardrail: answer truncated at max_tokens (model=%s, out=%s) — action item filed",
            getattr(gen, "model", "?"),
            getattr(gen, "output_tokens", "?"),
        )
    except Exception as exc:  # never let the guard break the answer path
        log.warning("guardrail: could not file truncation action item: %s", exc)
    return True
