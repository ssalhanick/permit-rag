"""
commerce/connectors/registry.py — name -> MaterialsConnector lookup for
real, catalog-backed retailers (see commerce/connectors/base.py).

A plain same-package dict, distinct from the cross-boundary DI pattern in
rag/agents/registry.py (which exists to solve "rag/ can't import commerce/
directly"). bids/ can already import commerce/ directly per AGENTS.md's
import boundaries, so this registry doesn't need that machinery — two
different problems, two different shapes.

commerce/connectors/manual.py is NOT registered here — it's a different
shape (direct entry, not catalog search); the bid form calls it directly.
"""

from __future__ import annotations

from commerce.connectors.base import MaterialsConnector
from commerce.serpapi_client import search_home_depot

_CONNECTORS: dict[str, MaterialsConnector] = {
    "home_depot": search_home_depot,
}


def register(name: str, connector: MaterialsConnector) -> None:
    """Add or replace a connector — the extension point for future real
    trade-account integrations (Home Depot Pro, Lowe's Pro, ...)."""
    _CONNECTORS[name] = connector


def get_connector(name: str) -> MaterialsConnector | None:
    return _CONNECTORS.get(name)


def list_connector_names() -> list[str]:
    return sorted(_CONNECTORS)
