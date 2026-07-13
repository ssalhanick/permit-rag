"""
rag/design_intent.py — Parse voice/text remodel intent into structured overlay patches.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

_DESIGN_SYSTEM = """\
You convert remodel instructions into structured AR overlay patches for a scanned room.
Return ONLY valid JSON with keys: overlays (array), explanation (string).
Each overlay object must include: surface_id (string or null), type (paint|tile|trim|appliance),
material_id (string), color_hex (string or null), asset_url (null unless appliance),
product_search (object with product_category, attributes dict, query string).
Use surface_id null when the target wall is ambiguous; the client may prompt the user.
Do not invent measurements. Use only the provided room context.
"""


def parse_design_intent(
    utterance: str,
    *,
    room_label: str | None = None,
    room_derived: dict[str, Any] | None = None,
    surface_hints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Parse a remodel utterance into overlay patches via the configured LLM provider.

    Falls back to a simple rule parser when Anthropic is unavailable (tests/local).
    """
    utterance = utterance.strip()
    if not utterance:
        return {"overlays": [], "explanation": "No instruction provided."}

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _with_usage(_parse_design_intent_rules(utterance, room_label=room_label), "rules")

    try:
        return _parse_design_intent_llm(
            utterance,
            room_label=room_label,
            room_derived=room_derived,
            surface_hints=surface_hints,
        )
    except Exception as exc:
        log.warning("design_intent LLM failed (%s); using rules fallback", exc)
        return _with_usage(_parse_design_intent_rules(utterance, room_label=room_label), "rules")


def _with_usage(result: dict[str, Any], model: str) -> dict[str, Any]:
    """Attach zero-token usage metadata to a parse result."""
    return {
        **result,
        "usage": {"input_tokens": 0, "output_tokens": 0, "model": model},
    }


def _parse_design_intent_rules(
    utterance: str,
    *,
    room_label: str | None = None,
) -> dict[str, Any]:
    """Lightweight keyword parser for offline/tests."""
    lower = utterance.lower()
    overlay_type = "paint"
    material_id = "generic_paint"
    color_hex = None

    if "tile" in lower or "subway" in lower:
        overlay_type = "tile"
        material_id = "white_subway_tile"
    elif "trim" in lower or "baseboard" in lower:
        overlay_type = "trim"
        material_id = "white_trim"
    elif any(word in lower for word in ("fridge", "refrigerator", "appliance", "oven", "range")):
        overlay_type = "appliance"
        material_id = "stainless_appliance"

    color_match = re.search(
        r"(#[0-9a-fA-F]{6}|sage|white|gray|grey|green|blue|black|beige|pewter)",
        lower,
    )
    if color_match:
        token = color_match.group(1)
        color_map = {
            "sage": "#9CAF88",
            "white": "#FFFFFF",
            "gray": "#808080",
            "grey": "#808080",
            "green": "#2E8B57",
            "blue": "#4A90D9",
            "black": "#111111",
            "beige": "#F5F5DC",
            "pewter": "#96A8A1",
        }
        color_hex = color_map.get(token, token if token.startswith("#") else None)

    return {
        "overlays": [
            {
                "surface_id": None,
                "type": overlay_type,
                "material_id": material_id,
                "color_hex": color_hex,
                "asset_url": None,
            }
        ],
        "explanation": f"Applied rule-based intent for {room_label or 'room'}: {utterance}",
    }


def _parse_design_intent_llm(
    utterance: str,
    *,
    room_label: str | None,
    room_derived: dict[str, Any] | None,
    surface_hints: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Call Anthropic for structured overlay patches."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    model = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
    context = {
        "room_label": room_label,
        "derived": room_derived or {},
        "surface_hints": surface_hints or [],
    }
    user_message = (
        f"Room context:\n{json.dumps(context, indent=2)}\n\n"
        f"User instruction:\n{utterance}\n\n"
        "Return JSON only."
    )
    response = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0.0,
        system=_DESIGN_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
    )
    text = response.content[0].text if response.content else "{}"
    parsed = json.loads(text)
    if "overlays" not in parsed:
        raise ValueError("LLM response missing overlays key")
    return {
        "overlays": parsed["overlays"],
        "explanation": parsed.get("explanation", ""),
        "usage": {
            "input_tokens": int(response.usage.input_tokens),
            "output_tokens": int(response.usage.output_tokens),
            "model": model,
        },
    }
