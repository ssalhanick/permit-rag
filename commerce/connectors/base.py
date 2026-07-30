"""
commerce/connectors/base.py — pluggable materials-connector interface for
real, catalog-backed retailers.

A structural (callable) Protocol, not an ABC: commerce/serpapi_client.search_home_depot
already matches this exact call signature, so it satisfies MaterialsConnector
as a connector with zero modification — no wrapper class needed. Future real
trade-account connectors (Home Depot Pro, Lowe's Pro — each needing
per-contractor OAuth/credential storage) implement the same signature and
register in commerce/connectors/registry.py.

commerce/connectors/manual.py is a deliberately DIFFERENT shape — it records
a contractor's direct, typed input rather than searching a catalog, since
there is nothing to search when a store has no connector. See that module's
docstring.
"""

from __future__ import annotations

from typing import Any, Protocol


class MaterialsConnector(Protocol):
    """Search a retailer's catalog by free-text query, localized by zip.
    Returns a list of ProductRef-shaped dicts (retailer, item_id, sku, title,
    price, price_unit, image_url, product_url, store_id, in_stock,
    pickup_available, price_as_of, zip_code) — the shape
    commerce/serpapi_client.search_home_depot already returns."""

    def __call__(self, query: str, *, zip_code: str, limit: int) -> list[dict[str, Any]]: ...
