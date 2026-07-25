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
from urllib.parse import urlparse
from uuid import UUID

log = logging.getLogger(__name__)

TRUNCATION_KIND = "answer_truncated"
UNSOURCED_MEDIA_KIND = "unsourced_media_url"
SOURCE_AGENT = "guardrail"

# The only host a media URL may come from unless it carries a curated-table
# marker. web_search is pinned to allowed_domains:["youtube.com"]; the curated
# media_refs table is youtube-only by CHECK constraint. Anything else is a
# model-invented (dead) link and must never reach the user.
ALLOWED_MEDIA_HOSTS: frozenset[str] = frozenset({"youtube.com"})


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


def _host(url: str) -> str:
    """Lowercased hostname of a URL, without the leading ``www.``."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_sourced(item: Any) -> bool:
    """True when a media item came from a vetted source.

    Two sourced paths (docs/agent_architecture.md #17): a row from the curated
    ``media_refs`` table (carries ``sourced=True``), or a URL on an allowed host
    (``youtube.com``, matched on the domain or any subdomain). Everything else is
    treated as a model-invented link and rejected.
    """
    if isinstance(item, dict):
        if item.get("sourced"):
            return True
        url = item.get("url") or ""
    else:
        if getattr(item, "sourced", False):
            return True
        url = getattr(item, "url", "") or ""
    host = _host(url)
    return any(host == a or host.endswith("." + a) for a in ALLOWED_MEDIA_HOSTS)


def check_media_sources(
    items: list[Any],
    *,
    run_id: UUID | None = None,
    entity_id: str | None = None,
) -> list[Any]:
    """Drop any media item whose URL is not from a vetted source.

    The hard gate behind the Media Curator's "zero unsourced URLs" contract.
    Returns only the sourced items; a dropped item files a deduped
    ``unsourced_media_url`` action item (evidence: the offending URL) so the
    anomaly detector can watch the rate. Never raises — a guard that can crash the
    answer path is worse than the link it drops. On the curated-table path nothing
    is ever dropped (every row is sourced); the gate does real work once
    web_search can propose model-emitted URLs.
    """
    if not items:
        return []
    kept = [it for it in items if _is_sourced(it)]
    dropped = [it for it in items if not _is_sourced(it)]
    if dropped:
        _file_unsourced_media(dropped, run_id=run_id, entity_id=entity_id)
    return kept


def _file_unsourced_media(
    dropped: list[Any],
    *,
    run_id: UUID | None,
    entity_id: str | None,
) -> None:
    """File one deduped action item recording rejected media URLs. Never raises."""
    def _url(it: Any) -> Any:
        return it.get("url") if isinstance(it, dict) else getattr(it, "url", None)

    urls = [_url(it) for it in dropped]
    try:
        from db.client import upsert_action_item

        upsert_action_item(
            source_agent=SOURCE_AGENT,
            kind=UNSOURCED_MEDIA_KIND,
            title="Media Curator produced an unsourced URL — dropped",
            severity="high",
            blocking=False,
            run_id=run_id,
            entity_type="query",
            entity_id=entity_id or (urls[0] if urls else "media"),
            evidence={"rejected_urls": urls},
            proposed_action=(
                "Investigate the media source path — a URL reached the Guardrail "
                "that was neither from media_refs nor an allowed host. Add the link "
                "to media_refs if legitimate, or tighten web_search allowed_domains."
            ),
        )
        log.warning("guardrail: dropped %d unsourced media URL(s): %s", len(urls), urls)
    except Exception as exc:  # never let the guard break the answer path
        log.warning("guardrail: could not file unsourced-media action item: %s", exc)
