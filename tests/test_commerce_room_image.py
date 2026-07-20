"""tests/test_commerce_room_image.py — room preview image generation."""

from __future__ import annotations

import base64

from commerce.room_image import (
    build_room_image_prompt,
    generate_room_preview_image,
    _parse_hex_color,
    _solid_png_bytes,
)


def test_parse_hex_color() -> None:
    """Hex parser should return RGB triples."""
    assert _parse_hex_color("#FF0000") == (255, 0, 0)
    assert _parse_hex_color("bad") == (200, 192, 180)


def test_solid_png_is_valid_png() -> None:
    """Mock PNG must start with PNG signature."""
    data = _solid_png_bytes((10, 20, 30), size=8)
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_build_prompt_includes_utterance_and_product() -> None:
    """Prompt should mention room label, utterance, and product title."""
    prompt = build_room_image_prompt(
        utterance="white subway tile",
        room_label="Kitchen",
        overlays=[
            {
                "type": "tile",
                "product_ref": {"title": "Daltile Subway Tile"},
            }
        ],
    )
    assert "Kitchen" in prompt
    assert "white subway tile" in prompt
    assert "Daltile Subway Tile" in prompt


def test_generate_falls_back_to_mock_without_api_key(monkeypatch) -> None:
    """Without API keys, generator returns mock PNG base64."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
    result = generate_room_preview_image(
        utterance="paint walls white",
        overlays=[{"color_hex": "#EEEEEE", "type": "paint"}],
        room_label="Bath",
    )
    assert result["provider"] == "mock"
    assert result["mock"] is True
    assert result["mime_type"] == "image/png"
    raw = base64.b64decode(result["image_base64"])
    assert raw.startswith(b"\x89PNG")
