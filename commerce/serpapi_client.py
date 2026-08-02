"""
commerce/serpapi_client.py — Home Depot product search via SerpApi (with offline fallback).
"""

from __future__ import annotations

import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SEC = 3600


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    """Return cached products if still fresh."""
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, products = entry
    if time.time() - ts > _CACHE_TTL_SEC:
        return None
    return products


def _cache_set(key: str, products: list[dict[str, Any]]) -> None:
    """Store products in the in-memory cache."""
    _CACHE[key] = (time.time(), products)


def _mock_products(query: str, zip_code: str) -> list[dict[str, Any]]:
    """Deterministic sample products when SerpApi is unavailable."""
    now = datetime.now(UTC).isoformat()
    base = query.lower()
    if "tile" in base or "subway" in base:
        return [
            {
                "retailer": "home_depot",
                "item_id": "203266473",
                "sku": "1003501234",
                "title": "Daltile Restore Bright White 3 in. x 6 in. Ceramic Subway Tile",
                "price": 0.98,
                "price_unit": "sq_ft",
                "image_url": "https://images.homedepot-static.com/productImages/example-tile.jpg",
                "product_url": "https://www.homedepot.com/p/example-tile",
                "store_id": "6841",
                "in_stock": True,
                "pickup_available": True,
                "price_as_of": now,
                "zip_code": zip_code,
            },
            {
                "retailer": "home_depot",
                "item_id": "203123456",
                "sku": "1001234567",
                "title": "Jeffrey Court Strada White 3 in. x 6 in. Ceramic Wall Tile",
                "price": 1.29,
                "price_unit": "sq_ft",
                "image_url": "https://images.homedepot-static.com/productImages/example-tile2.jpg",
                "product_url": "https://www.homedepot.com/p/example-tile2",
                "store_id": "6841",
                "in_stock": True,
                "pickup_available": True,
                "price_as_of": now,
                "zip_code": zip_code,
            },
        ]
    if "paint" in base:
        return [
            {
                "retailer": "home_depot",
                "item_id": "205123001",
                "sku": "2001234567",
                "title": "BEHR Premium Plus Ultra Pure White Interior Paint (1 gal.)",
                "price": 42.98,
                "price_unit": "each",
                "image_url": "https://images.homedepot-static.com/productImages/example-paint.jpg",
                "product_url": "https://www.homedepot.com/p/example-paint",
                "store_id": "6841",
                "in_stock": True,
                "pickup_available": True,
                "price_as_of": now,
                "zip_code": zip_code,
            },
        ]
    return [
        {
            "retailer": "home_depot",
            "item_id": "300000001",
            "sku": "3000000001",
            "title": f"Home Depot match: {query[:60]}",
            "price": 19.99,
            "price_unit": "each",
            "image_url": None,
            "product_url": f"https://www.homedepot.com/s/{urllib.parse.quote(query)}",
            "store_id": "6841",
            "in_stock": True,
            "pickup_available": False,
            "price_as_of": now,
            "zip_code": zip_code,
        },
    ]


def _parse_serpapi_product(item: dict[str, Any], zip_code: str) -> dict[str, Any] | None:
    """Normalize one SerpApi Home Depot product result."""
    now = datetime.now(UTC).isoformat()
    product_id = item.get("product_id") or item.get("item_id")
    title = item.get("title")
    if not product_id or not title:
        return None
    price_raw = item.get("price")
    price = None
    price_unit = "each"
    if isinstance(price_raw, (int, float)):
        price = float(price_raw)
    elif isinstance(price_raw, str):
        cleaned = price_raw.replace("$", "").replace(",", "").strip()
        try:
            price = float(cleaned.split()[0])
        except (ValueError, IndexError):
            price = None
        if "sq" in price_raw.lower():
            price_unit = "sq_ft"
    link = item.get("link") or item.get("url")
    availability = (item.get("availability") or item.get("availability_type") or "").lower()
    in_stock = "out" not in availability and "unavailable" not in availability
    return {
        "retailer": "home_depot",
        "item_id": str(product_id),
        "sku": str(item.get("store_sku_number") or item.get("sku") or product_id),
        "title": str(title),
        "price": price,
        "price_unit": price_unit,
        "image_url": item.get("thumbnail") or item.get("image"),
        "product_url": link,
        "store_id": str(item.get("store_id") or ""),
        "in_stock": in_stock,
        "pickup_available": "pickup" in availability or in_stock,
        "price_as_of": now,
        "zip_code": zip_code,
    }


def search_home_depot(
    query: str,
    *,
    zip_code: str = "75034",
    limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Search Home Depot products localized by zip via SerpApi.

    Falls back to mock catalog when SERPAPI_API_KEY is unset or the request fails.

    Args:
        query: Search keywords.
        zip_code: Delivery zip for localized pricing.
        limit: Max products to return.

    Returns:
        List of normalized product_ref dicts.
    """
    query = query.strip()
    if not query:
        return []

    cache_key = f"hd:{zip_code}:{query.lower()}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    api_key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not api_key:
        products = _mock_products(query, zip_code)[:limit]
        _cache_set(cache_key, products)
        return products

    params = urllib.parse.urlencode(
        {
            "engine": "home_depot",
            "q": query,
            "delivery_zip": zip_code,
            "api_key": api_key,
        }
    )
    url = f"https://serpapi.com/search.json?{params}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            import json

            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # HTTPError is a URLError subclass, so a bare `except URLError` here
        # would silently swallow the response body — surfacing it because a
        # SerpApi plan/quota rejection (e.g. an engine not included on the
        # free tier) looks identical to a network failure otherwise.
        detail = exc.read().decode("utf-8", errors="replace")
        log.warning(
            "SerpApi Home Depot search failed: HTTP %s %s — %s; using mock products",
            exc.code, exc.reason, detail,
        )
        products = _mock_products(query, zip_code)[:limit]
        _cache_set(cache_key, products)
        return products
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log.warning("SerpApi Home Depot search failed (%s); using mock products", exc)
        products = _mock_products(query, zip_code)[:limit]
        _cache_set(cache_key, products)
        return products

    raw_items = payload.get("products") or []
    if not raw_items and payload.get("product_results"):
        raw_items = [payload["product_results"]]

    products: list[dict[str, Any]] = []
    for item in raw_items:
        normalized = _parse_serpapi_product(item, zip_code)
        if normalized:
            products.append(normalized)
        if len(products) >= limit:
            break

    if not products:
        # Request succeeded (200 OK) but nothing usable came out of it —
        # log what SerpApi actually sent back so a shape mismatch is
        # diagnosable instead of looking identical to "key not working."
        log.warning(
            "SerpApi Home Depot search returned 0 usable products for %r (top-level response keys: %s); using mock products",
            query, list(payload.keys()),
        )
        products = _mock_products(query, zip_code)[:limit]

    _cache_set(cache_key, products)
    return products
