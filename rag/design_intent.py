"""
rag/design_intent.py — Parse voice/text remodel intent into structured overlay patches.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from rag.agent_runtime import Tier, run_agent

log = logging.getLogger(__name__)

_DESIGN_SYSTEM = """\
You convert remodel instructions into structured AR overlay patches for a scanned room.
Return ONLY valid JSON with keys: overlays (array), explanation (string).
Each overlay object must include:
- surface_id: (string or null). If selected_surface_id is provided in context, target that surface_id primarily unless instruction implies another wall.
- type: (paint|tile|trim|appliance)
- material_id: (string)
- color_hex: (string or null)
- asset_url: (null unless appliance)
- product_search: (object with product_category, attributes dict, query string)
- y_min: (float, optional, default 0.0). Fractional lower height boundary of the texture segment on the wall (from 0.0 to 1.0).
- y_max: (float, optional, default 1.0). Fractional upper height boundary of the texture segment on the wall (from 0.0 to 1.0).
- x_min: (float, optional, default 0.0). Fractional left boundary (from 0.0 to 1.0).
- x_max: (float, optional, default 1.0). Fractional right boundary (from 0.0 to 1.0).

Wall Bisection / Splits:
If the user wants different textures on parts of the same wall (e.g. "backsplash on bottom half"), return MULTIPLE overlays for that surface_id representing segments. E.g.:
1. Tile backsplash on bottom half: y_min: 0.0, y_max: 0.5, type: tile, material_id: white_subway_tile.
2. Paint on top half: y_min: 0.5, y_max: 1.0, type: paint, material_id: generic_paint.
Calculate these boundaries based on the wall dimensions in surface_hints if user specifies exact units (e.g. "bottom 1 meter" on a wall with height 2.5m is y_min: 0.0, y_max: 0.4).
Do not invent measurements. Use only the provided room context.
"""


# ── Structured-output schema (messages.parse) ────────────────
# The runtime uses these to constrain decoding, so the model cannot return a
# malformed overlay. extra="allow" keeps forward-compatibility with any new
# hint the prompt starts emitting before this schema catches up.


class OverlayPatch(BaseModel):
    """One AR overlay segment applied to a scanned surface."""

    model_config = ConfigDict(extra="allow")

    surface_id: str | None = None
    type: Literal["paint", "tile", "trim", "appliance"] = "paint"
    material_id: str = "generic_paint"
    color_hex: str | None = None
    asset_url: str | None = None
    product_search: dict[str, Any] | None = None
    y_min: float = 0.0
    y_max: float = 1.0
    x_min: float = 0.0
    x_max: float = 1.0


class DesignIntentParse(BaseModel):
    """The structured result of parsing one remodel utterance."""

    overlays: list[OverlayPatch] = Field(default_factory=list)
    explanation: str = ""


def parse_design_intent(
    utterance: str,
    *,
    room_label: str | None = None,
    room_derived: dict[str, Any] | None = None,
    surface_hints: list[dict[str, Any]] | None = None,
    selected_surface_id: str | None = None,
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
        return _with_usage(_parse_design_intent_rules(utterance, room_label=room_label, selected_surface_id=selected_surface_id), "rules")

    try:
        return _parse_design_intent_llm(
            utterance,
            room_label=room_label,
            room_derived=room_derived,
            surface_hints=surface_hints,
            selected_surface_id=selected_surface_id,
        )
    except Exception as exc:
        log.warning("design_intent LLM failed (%s); using rules fallback", exc)
        return _with_usage(_parse_design_intent_rules(utterance, room_label=room_label, selected_surface_id=selected_surface_id), "rules")


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
    selected_surface_id: str | None = None,
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
                "surface_id": selected_surface_id,
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
    selected_surface_id: str | None = None,
) -> dict[str, Any]:
    """
    Parse structured overlay patches through the agent runtime.

    Uses ``messages.parse`` (via ``run_agent``) so the overlays are
    schema-valid by construction -- no JSON repair. Tracing, model-ladder
    selection, caching, and autonomy all happen inside the runtime; this
    function only assembles the prompt and reshapes the validated result into
    the dict contract callers (and token accounting) already expect.
    """
    context = {
        "room_label": room_label,
        "derived": room_derived or {},
        "surface_hints": surface_hints or [],
        "selected_surface_id": selected_surface_id,
    }
    user_message = (
        f"Room context:\n{json.dumps(context, indent=2)}\n\n"
        f"User instruction:\n{utterance}\n\n"
        "Return the structured overlays."
    )
    result = run_agent(
        "design_intent",
        system=_DESIGN_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        tier=Tier.CHEAP,
        output_format=DesignIntentParse,
        effort="low",
        max_tokens=512,
        temperature=0.0,
        input_parts=(utterance, selected_surface_id),
    )
    parsed = result.parsed_output
    if parsed is None:
        raise ValueError("LLM response missing overlays key")
    return {
        "overlays": [o.model_dump() for o in parsed.overlays],
        "explanation": parsed.explanation,
        "usage": {
            "input_tokens": result.usage.tokens_in,
            "output_tokens": result.usage.tokens_out,
            "model": result.model,
        },
    }
