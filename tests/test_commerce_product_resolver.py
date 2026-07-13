"""
tests/test_commerce_product_resolver.py — product resolution without SerpApi key.
"""

from __future__ import annotations

from commerce.product_resolver import build_product_search, resolve_products_for_overlays


def test_build_product_search_tile() -> None:
    """Tile overlay should produce a subway tile search query."""
    search = build_product_search(
        {"type": "tile", "material_id": "white_subway_tile"},
        "white subway tile backsplash",
    )
    assert search["product_category"] == "subway_tile"
    assert "tile" in search["query"].lower()


def test_resolve_products_for_overlays_mock() -> None:
    """Resolver should attach product_ref and qty_estimate without API key."""
    overlays = [
        {
            "surface_id": None,
            "type": "tile",
            "material_id": "white_subway_tile",
            "color_hex": "#F8F8F8",
            "asset_url": None,
        }
    ]
    enriched, candidates = resolve_products_for_overlays(
        overlays,
        room_derived={"floor_area_sqm": 8, "wall_count": 4},
        zip_code="75034",
        utterance="white subway tile backsplash",
    )
    assert len(enriched) == 1
    assert enriched[0]["product_ref"] is not None
    assert enriched[0]["product_ref"]["retailer"] == "home_depot"
    assert enriched[0].get("qty_estimate") is not None
    assert len(candidates) >= 1
