"""
tests/test_gis.py — Unit tests for the GIS jurisdiction lookup functions.
"""

from rag.gis import lookup_jurisdiction_overlays


def test_lookup_dallas_swiss_avenue() -> None:
    """Swiss Avenue coordinates should fall inside Swiss Avenue Historic District."""
    # (lat, lng) = (32.805, -96.77)
    historic, conservation = lookup_jurisdiction_overlays("Dallas", 32.805, -96.77)
    assert historic == "Swiss Avenue Historic District"
    assert conservation is None


def test_lookup_dallas_m_streets() -> None:
    """M-Streets coordinates should fall inside M-Streets Conservation District."""
    # (lat, lng) = (32.825, -96.76)
    historic, conservation = lookup_jurisdiction_overlays("Dallas", 32.825, -96.76)
    assert historic is None
    assert conservation == "M-Streets Conservation District"


def test_lookup_outside() -> None:
    """Coordinates far away or missing should return None."""
    historic, conservation = lookup_jurisdiction_overlays("Dallas", 30.0, -90.0)
    assert historic is None
    assert conservation is None

    historic, conservation = lookup_jurisdiction_overlays(None, 32.805, -96.77)
    assert historic is None
    assert conservation is None
