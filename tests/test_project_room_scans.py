"""
tests/test_project_room_scans.py — room-scans API and db helpers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from db import client as db_client


def test_room_summary_mirror_payload_serializes_datetime() -> None:
    """Mirror payload must JSON-serialize datetime captured_at values."""
    import json
    from datetime import UTC, datetime

    from db.client import _room_summary_mirror_payload

    captured = datetime(2026, 7, 12, tzinfo=UTC)
    payload = _room_summary_mirror_payload(
        room_label="Kitchen",
        section="kitchen",
        captured_at=captured,
        derived={"wall_count": 4},
    )
    encoded = json.dumps(payload)
    assert "2026-07-12" in encoded


def test_upsert_project_room_scans_mirrors_active_room_summary() -> None:
    """Active room row should mirror projects.room_summary."""
    project_id = uuid4()
    structure_id = uuid4()
    kitchen_id = uuid4()
    captured = datetime(2026, 7, 12, tzinfo=UTC)

    with patch.object(db_client, "get_conn") as mock_conn:
        conn = mock_conn.return_value.__enter__.return_value
        # Each upsert returns its row: an empty RETURNING now means the id
        # belongs to another project and raises.
        conn.execute.return_value.fetchone.side_effect = [
            {"id": structure_id, "room_label": "Whole house"},
            {"id": kitchen_id, "room_label": "Kitchen", "captured_at": captured, "derived": {"wall_count": 4}},
        ]
        conn.execute.return_value.fetchall.return_value = [
            {
                "id": structure_id,
                "scan_type": "structure",
                "room_label": "Whole house",
                "is_active": False,
            },
            {
                "id": kitchen_id,
                "scan_type": "room",
                "room_label": "Kitchen",
                "is_active": True,
            },
        ]

        db_client.upsert_project_room_scans(
            project_id,
            [
                {
                    "id": structure_id,
                    "scan_type": "structure",
                    "parent_scan_id": None,
                    "room_label": "Whole house",
                    "section": None,
                    "captured_at": captured,
                    "derived": {"room_count": 1},
                    "is_active": False,
                },
                {
                    "id": kitchen_id,
                    "scan_type": "room",
                    "parent_scan_id": structure_id,
                    "room_label": "Kitchen",
                    "section": "kitchen",
                    "captured_at": captured,
                    "derived": {"wall_count": 4},
                    "is_active": True,
                },
            ],
        )

        update_calls = [
            call.args[0]
            for call in conn.execute.call_args_list
            if "room_summary" in str(call.args[0])
        ]
        assert update_calls, "expected room_summary mirror update"


def test_upsert_user_room_scans_rejects_another_users_scan_id() -> None:
    """
    Scan ids come from the client, so an id owned by another user must fail.

    The ON CONFLICT branch is scoped to the caller, so a foreign id updates no
    row and returns none — that has to raise rather than silently no-op.
    """
    with patch.object(db_client, "get_conn") as mock_conn:
        conn = mock_conn.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = None

        with pytest.raises(PermissionError, match="another user's library"):
            db_client.upsert_user_room_scans(
                uuid4(),
                [
                    {
                        "id": uuid4(),
                        "scan_type": "room",
                        "parent_scan_id": None,
                        "room_label": "Kitchen",
                        "section": None,
                        "structure_label": None,
                        "captured_at": datetime(2026, 7, 12, tzinfo=UTC),
                        "derived": {"wall_count": 4},
                    }
                ],
            )
        conn.commit.assert_not_called()


def test_upsert_user_room_scans_upsert_is_scoped_to_caller() -> None:
    """The ownership predicate must be part of the ON CONFLICT statement."""
    user_id = uuid4()
    with patch.object(db_client, "get_conn") as mock_conn:
        conn = mock_conn.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = {"id": uuid4()}
        conn.execute.return_value.fetchall.return_value = []

        db_client.upsert_user_room_scans(
            user_id,
            [
                {
                    "id": uuid4(),
                    "scan_type": "room",
                    "parent_scan_id": None,
                    "room_label": "Kitchen",
                    "section": None,
                    "structure_label": None,
                    "captured_at": datetime(2026, 7, 12, tzinfo=UTC),
                    "derived": {"wall_count": 4},
                }
            ],
        )

    upserts = [
        call.args[0]
        for call in conn.execute.call_args_list
        if "ON CONFLICT" in str(call.args[0])
    ]
    assert upserts, "expected an upsert statement"
    assert "WHERE user_room_scans.user_id" in upserts[0]


def test_upsert_project_room_scans_rejects_another_projects_scan_id() -> None:
    """A project editor must not be able to overwrite another project's row."""
    with patch.object(db_client, "get_conn") as mock_conn:
        conn = mock_conn.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = None

        with pytest.raises(PermissionError, match="another project"):
            db_client.upsert_project_room_scans(
                uuid4(),
                [
                    {
                        "id": uuid4(),
                        "scan_type": "room",
                        "parent_scan_id": None,
                        "room_label": "Kitchen",
                        "section": None,
                        "captured_at": datetime(2026, 7, 12, tzinfo=UTC),
                        "derived": {"wall_count": 4},
                        "is_active": False,
                    }
                ],
            )
        conn.commit.assert_not_called()


def test_parse_design_intent_rules_tile() -> None:
    """Rule fallback should detect tile intent without API key."""
    from rag.design_intent import parse_design_intent

    result = parse_design_intent("white subway tile on backsplash")
    assert result["overlays"][0]["type"] == "tile"
    assert result["overlays"][0]["material_id"] == "white_subway_tile"


def test_format_project_context_block_includes_room() -> None:
    """Project context formatter should include active room metrics."""
    from rag.project_context import format_project_context_block

    block = format_project_context_block(
        {
            "project_name": "123 Main",
            "municipality": "plano",
            "active_room": {
                "room_label": "Kitchen",
                "derived": {"wall_count": 4, "max_ceiling_height_m": 2.4},
            },
        }
    )
    assert "Kitchen" in block
    assert "Walls detected: 4" in block
