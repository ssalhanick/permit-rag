"""
commerce/room_image.py — generative room redesign preview images.
=================================================================
Uses OpenAI Images API when OPENAI_API_KEY is set; otherwise returns a
deterministic mock PNG tinted from overlay colors (offline demos).
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
import urllib.error
import urllib.request
import zlib
from typing import Any

log = logging.getLogger(__name__)

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
OPENAI_EDITS_URL = "https://api.openai.com/v1/images/edits"
DEFAULT_MODEL = "gpt-image-1"
MOCK_SIZE = 256

LEONARDO_GENERATIONS_URL = "https://cloud.leonardo.ai/api/rest/v1/generations"
LEONARDO_DEFAULT_MODEL = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"  # Phoenix


def _leonardo_generate(prompt: str, model: str, tiling: bool) -> str:
    """Call Leonardo.ai REST API (v1); poll for asynchronous completion, return base64."""
    api_key = os.environ.get("LEONARDO_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("LEONARDO_API_KEY not set")

    body = {
        "prompt": prompt,
        "modelId": model,
        "width": 1024,
        "height": 768,
        "num_images": 1,
        "tiling": tiling,
    }

    req = urllib.request.Request(
        LEONARDO_GENERATIONS_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    job = payload.get("sdGenerationJob") or {}
    generation_id = job.get("generationId")
    if not generation_id:
        raise RuntimeError("Leonardo generation failed to start (no generationId returned)")

    # Poll status
    poll_url = f"{LEONARDO_GENERATIONS_URL}/{generation_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
    }

    # Poll up to 30 times (60 seconds max)
    for _ in range(30):
        time.sleep(2)
        poll_req = urllib.request.Request(poll_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(poll_req, timeout=30) as poll_resp:
                poll_payload = json.loads(poll_resp.read().decode("utf-8"))
            
            gen_pk = poll_payload.get("generations_by_pk") or {}
            status = gen_pk.get("status")
            if status == "COMPLETE":
                images = gen_pk.get("generated_images") or []
                if not images:
                    raise RuntimeError("Leonardo generation complete but no images found")
                url = images[0].get("url")
                if not url:
                    raise RuntimeError("Leonardo image record missing URL")
                
                # Fetch the image bytes and base64-encode them
                with urllib.request.urlopen(url, timeout=45) as img_resp:
                    return base64.b64encode(img_resp.read()).decode("ascii")
            elif status == "FAILED":
                raise RuntimeError("Leonardo generation job failed")
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            log.warning("Leonardo polling encountered error: %s", e)

    raise RuntimeError("Leonardo generation timed out after 60 seconds")


def _parse_hex_color(color_hex: str | None) -> tuple[int, int, int]:
    """Parse #RRGGBB into RGB bytes; default warm gray."""
    raw = (color_hex or "#C8C0B4").lstrip("#")
    if len(raw) != 6:
        return (200, 192, 180)
    try:
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    except ValueError:
        return (200, 192, 180)


def _solid_png_bytes(rgb: tuple[int, int, int], size: int = MOCK_SIZE) -> bytes:
    """Build a minimal solid-color PNG with stdlib only."""
    r, g, b = rgb
    raw_rows = b"".join(
        b"\x00" + bytes([r, g, b]) * size for _ in range(size)
    )
    compressed = zlib.compress(raw_rows, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def build_room_image_prompt(
    *,
    utterance: str,
    room_label: str | None,
    overlays: list[dict[str, Any]],
) -> str:
    """Compose a text-to-image prompt from design-intent overlays."""
    materials: list[str] = []
    for overlay in overlays:
        product = overlay.get("product_ref") or {}
        title = product.get("title")
        if title:
            materials.append(str(title))
            continue
        mid = overlay.get("material_id") or overlay.get("type") or "finish"
        hex_color = overlay.get("color_hex") or ""
        materials.append(f"{mid} {hex_color}".strip())
    material_text = "; ".join(materials[:6]) if materials else utterance
    label = room_label or "residential room"
    return (
        f"Photoreal interior photo of a {label} remodel. "
        f"Apply these materials: {material_text}. "
        f"User request: {utterance}. "
        "Natural daylight, realistic architecture, no text overlays, no logos."
    )


def _openai_generate(prompt: str, model: str) -> str:
    """Call OpenAI images.generations; return base64 PNG/JPEG payload."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024",
    }
    if model.startswith("dall-e"):
        body["response_format"] = "b64_json"

    req = urllib.request.Request(
        OPENAI_IMAGES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    data = (payload.get("data") or [{}])[0]
    b64 = data.get("b64_json")
    if not b64 and data.get("url"):
        with urllib.request.urlopen(data["url"], timeout=60) as img_resp:
            b64 = base64.b64encode(img_resp.read()).decode("ascii")
    if not b64:
        raise RuntimeError("OpenAI image response missing image data")
    return b64


def _mock_generate(overlays: list[dict[str, Any]]) -> str:
    """Offline placeholder PNG tinted from the first overlay color."""
    color = None
    if overlays:
        color = overlays[0].get("color_hex")
    png = _solid_png_bytes(_parse_hex_color(color))
    return base64.b64encode(png).decode("ascii")


def generate_room_preview_image(
    *,
    utterance: str,
    overlays: list[dict[str, Any]] | None = None,
    room_label: str | None = None,
    source_image_b64: str | None = None,
    tiling: bool | None = None,
) -> dict[str, Any]:
    """
    Generate a room redesign preview image.

    Prefers Leonardo when LEONARDO_API_KEY is set, then OpenAI when OPENAI_API_KEY is set.
    Optional source_image_b64 is reserved for future img2img edits; currently folded
    into the text prompt.

    Returns:
        Dict with image_base64, mime_type, provider, prompt, model.
    """
    overlay_rows = overlays or []
    prompt = build_room_image_prompt(
        utterance=utterance,
        room_label=room_label,
        overlays=overlay_rows,
    )
    if source_image_b64:
        prompt = (
            f"{prompt} Match the camera angle and layout of the provided room photo."
        )

    leonardo_key = os.environ.get("LEONARDO_API_KEY", "").strip()
    if leonardo_key:
        model = os.environ.get("LEONARDO_IMAGE_MODEL", LEONARDO_DEFAULT_MODEL).strip() or LEONARDO_DEFAULT_MODEL
        try:
            b64 = _leonardo_generate(prompt, model, tiling=bool(tiling))
            return {
                "image_base64": b64,
                "mime_type": "image/png",
                "provider": "leonardo",
                "model": model,
                "prompt": prompt,
                "mock": False,
            }
        except Exception as exc:
            log.warning("Leonardo room image failed (%s); falling back", exc)

    model = os.environ.get("OPENAI_IMAGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if openai_key:
        try:
            b64 = _openai_generate(prompt, model)
            return {
                "image_base64": b64,
                "mime_type": "image/png",
                "provider": "openai",
                "model": model,
                "prompt": prompt,
                "mock": False,
            }
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
            log.warning("OpenAI room image failed (%s); using mock", exc)

    return {
        "image_base64": _mock_generate(overlay_rows),
        "mime_type": "image/png",
        "provider": "mock",
        "model": "mock-solid-png",
        "prompt": prompt,
        "mock": True,
    }
