"""
tests/test_project_context.py — Unit tests for project context loading and formatting.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4
from unittest.mock import patch

from rag.project_context import load_project_context, format_project_context_block


def test_load_project_context_no_active_room() -> None:
    """It should load basic project context when there is no active room scan."""
    pid = uuid4()
    dummy_project = {
        "id": pid,
        "name": "Test Kitchen Project",
        "municipality": "Dallas",
        "address": "123 Test St",
        "spaces": ["Kitchen"],
        "work_types": ["Plumbing"],
        "recommended_permits": ["Plumbing Permit"],
        "budget": "$15k",
        "persona": "diy",
        "custom_system_prompt": "DIY compliance instructions",
    }

    with patch("db.client.get_project", return_value=dummy_project), \
         patch("db.client.get_active_room_scan", return_value=None):
        ctx = load_project_context(pid)

    assert ctx is not None
    assert ctx["project_name"] == "Test Kitchen Project"
    assert ctx["budget"] == "$15k"
    assert ctx["persona"] == "diy"
    assert ctx["custom_system_prompt"] == "DIY compliance instructions"
    assert "active_room" not in ctx


def test_format_project_context_block_with_room() -> None:
    """It should format project details and active room metrics correctly."""
    context = {
        "project_name": "Modern Bath",
        "municipality": "Plano",
        "address": "456 Oak Ave",
        "spaces": ["Bathroom"],
        "work_types": ["Electrical", "Plumbing"],
        "recommended_permits": ["Electrical Permit", "Plumbing Permit"],
        "budget": "$20k",
        "persona": "contractor",
        "active_room": {
            "room_label": "Master Bath",
            "section": "first_floor",
            "derived": {
                "wall_count": 4,
                "max_ceiling_height_m": 2.7,
                "floor_area_sqm": 12.5,
                "wall_lengths_m": [3.0, 4.0, 3.0, 4.0],
            },
        },
    }

    formatted = format_project_context_block(context)

    # Verify formatting output
    assert "Project: Modern Bath" in formatted
    assert "Municipality: Plano" in formatted
    assert "Spaces: Bathroom" in formatted
    assert "Work types: Electrical, Plumbing" in formatted
    assert "Budget: $20k" in formatted
    assert "Persona: contractor" in formatted
    assert "Active room: Master Bath" in formatted
    assert "Walls detected: 4" in formatted
    assert "Max ceiling height (m): 2.7" in formatted
    assert "Floor area (m²): 12.5" in formatted
    assert "Wall lengths (m): 3.0, 4.0, 3.0, 4.0" in formatted
