"""
rag/project_context.py — Build non-cited project context for answer generation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from db import client as db_client


def load_project_context(project_id: UUID | str) -> dict[str, Any] | None:
    """
    Load kickoff fields and active room derived metrics for RAG context.

    Returns None when the project is missing or has no active room scan.
    """
    pid = UUID(str(project_id)) if not isinstance(project_id, UUID) else project_id
    project = db_client.get_project(pid)
    if not project:
        return None

    active_room = db_client.get_active_room_scan(pid)
    context: dict[str, Any] = {
        "project_name": project.get("name"),
        "municipality": project.get("municipality"),
        "address": project.get("address"),
        "spaces": project.get("spaces") or [],
        "work_types": project.get("work_types") or [],
        "recommended_permits": project.get("recommended_permits") or [],
        "budget": project.get("budget"),
        "persona": project.get("persona"),
        # Phase 4: the Prompt Router reads persona/experience/project_notes.
        # custom_system_prompt is retained for rows written before the kickoff
        # demotion (the router falls back to it when project_notes is empty).
        "experience": project.get("experience"),
        "project_notes": project.get("project_notes"),
        "custom_system_prompt": project.get("custom_system_prompt"),
    }
    if active_room:
        context["active_room"] = {
            "room_label": active_room.get("room_label"),
            "section": active_room.get("section"),
            "captured_at": active_room.get("captured_at"),
            "derived": active_room.get("derived") or {},
        }
    return context


def format_project_context_block(context: dict[str, Any] | None) -> str:
    """Format project context for the LLM user message (facts, not citations)."""
    if not context:
        return ""

    lines = ["Project context (measurements are user-provided facts, not code sources):"]
    if context.get("project_name"):
        lines.append(f"- Project: {context['project_name']}")
    if context.get("municipality"):
        lines.append(f"- Municipality: {context['municipality']}")
    if context.get("address"):
        lines.append(f"- Address: {context['address']}")
    if context.get("spaces"):
        lines.append(f"- Spaces: {', '.join(context['spaces'])}")
    if context.get("work_types"):
        lines.append(f"- Work types: {', '.join(context['work_types'])}")
    if context.get("recommended_permits"):
        lines.append(f"- Recommended permits: {', '.join(context['recommended_permits'])}")
    if context.get("persona"):
        lines.append(f"- Persona: {context['persona']}")
    if context.get("budget"):
        lines.append(f"- Budget: {context['budget']}")

    room = context.get("active_room")
    if room:
        derived = room.get("derived") or {}
        lines.append(f"- Active room: {room.get('room_label', 'room')}")
        if room.get("section"):
            lines.append(f"- Room section: {room['section']}")
        if derived.get("wall_count") is not None:
            lines.append(f"- Walls detected: {derived['wall_count']}")
        if derived.get("max_ceiling_height_m") is not None:
            lines.append(f"- Max ceiling height (m): {derived['max_ceiling_height_m']}")
        # Scans synced before floor and wall area were split stored wall area
        # under the floor_area_sqm name. Report those as wall area so the model
        # never reasons about a floor dimension it was never given.
        if derived.get("wall_area_sqm") is None:
            if derived.get("floor_area_sqm") is not None:
                lines.append(f"- Wall surface area (m²): {derived['floor_area_sqm']}")
        else:
            lines.append(f"- Wall surface area (m²): {derived['wall_area_sqm']}")
            if derived.get("floor_area_sqm") is not None:
                estimated = derived.get("floor_area_source") == "wall_footprint"
                note = " (estimated from wall footprint)" if estimated else ""
                lines.append(f"- Floor area (m²): {derived['floor_area_sqm']}{note}")
        lengths = derived.get("wall_lengths_m") or []
        if lengths:
            lines.append(f"- Wall lengths (m): {', '.join(str(v) for v in lengths)}")

    return "\n".join(lines)
