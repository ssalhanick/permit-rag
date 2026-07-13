"""
tests/test_room_design_intent.py — design-intent routes and token accounting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest

from api.schemas import DesignIntentRequest
from db import client as db_client


def test_parse_design_intent_includes_usage() -> None:
    """Rule fallback should include zero-token usage metadata."""
    from rag.design_intent import parse_design_intent

    result = parse_design_intent("white subway tile")
    assert "usage" in result
    assert result["usage"]["model"] == "rules"
    assert result["usage"]["input_tokens"] == 0


def test_insert_design_intent_usage_writes_row() -> None:
    """insert_design_intent_usage should execute insert with expected params."""
    user_id = uuid4()
    project_id = uuid4()
    scan_id = uuid4()

    with patch.object(db_client, "get_conn") as mock_conn:
        conn = mock_conn.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = {
            "id": uuid4(),
            "user_id": user_id,
            "input_tokens": 10,
            "output_tokens": 20,
            "model": "rules",
        }
        row = db_client.insert_design_intent_usage(
            user_id=user_id,
            project_id=project_id,
            room_scan_id=scan_id,
            input_tokens=10,
            output_tokens=20,
            model="rules",
        )
        assert row["input_tokens"] == 10


def test_sum_design_intent_tokens_returns_total() -> None:
    """sum_design_intent_tokens should return aggregated token count."""
    user_id = uuid4()
    since = datetime(2026, 7, 1, tzinfo=UTC)

    with patch.object(db_client, "get_conn") as mock_conn:
        conn = mock_conn.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = {"total": 1500}
        total = db_client.sum_design_intent_tokens(user_id, since=since)
        assert total == 1500


def test_check_token_cap_raises_when_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monthly cap should return HTTP 429 when exceeded."""
    from fastapi import HTTPException

    from api.design_intent_helpers import _check_token_cap

    monkeypatch.setenv("DESIGN_INTENT_MONTHLY_TOKEN_CAP", "100")
    user_id = uuid4()

    with patch.object(db_client, "sum_design_intent_tokens", return_value=200):
        with pytest.raises(HTTPException) as exc:
            _check_token_cap(user_id)
        assert exc.value.status_code == 429


def test_run_design_intent_returns_usage() -> None:
    """run_design_intent should return overlays and usage fields."""
    from api.design_intent_helpers import run_design_intent

    user_id = uuid4()
    project_id = uuid4()
    scan_id = uuid4()
    body = DesignIntentRequest(utterance="sage green paint")

    with patch("api.design_intent_helpers._check_token_cap"), patch(
        "rag.design_intent.parse_design_intent",
        return_value={
            "overlays": [{"type": "paint", "material_id": "generic_paint"}],
            "explanation": "ok",
            "usage": {"input_tokens": 0, "output_tokens": 0, "model": "rules"},
        },
    ), patch(
        "commerce.product_resolver.resolve_products_for_overlays",
        return_value=([{"type": "paint"}], []),
    ), patch.object(db_client, "insert_design_intent_usage", return_value={}), patch.object(
        db_client, "get_project", return_value={"address": "Plano TX 75034"},
    ):
        result = run_design_intent(
            user_id=user_id,
            project_id=project_id,
            scan_id=scan_id,
            room_row={"room_label": "Kitchen", "derived": {"wall_count": 4}},
            body=body,
        )

    assert result["usage"]["model"] == "rules"
    assert len(result["overlays"]) == 1


def test_resolve_room_scan_row_rejects_structure() -> None:
    """Resolver should 404 when scan is not a room row."""
    from fastapi import HTTPException

    from api.design_intent_helpers import _resolve_room_scan_row

    scan_id = uuid4()
    with pytest.raises(HTTPException) as exc:
        _resolve_room_scan_row(
            [{"id": scan_id, "scan_type": "structure", "room_label": "House"}],
            scan_id,
        )
    assert exc.value.status_code == 404
