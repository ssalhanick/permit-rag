"""tests/test_room_preview_image_route.py — commerce room image API."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_room_preview_image_returns_mock_without_openai(monkeypatch) -> None:
    """Route should return mock PNG payload when keys are absent."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
    monkeypatch.setenv("API_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "false")

    from api.main import app
    from api.auth import get_current_user
    from db import client as db_client

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "role": "owner",
    }
    client = TestClient(app)
    try:
        # The route meters generations per user; keep this a unit test.
        with patch.object(db_client, "count_design_intent_usage", return_value=0):
            resp = client.post(
                "/api/commerce/room-preview-image",
                json={
                    "utterance": "white subway tile",
                    "room_label": "Kitchen",
                    "overlays": [{"type": "tile", "color_hex": "#F8F8F8"}],
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "mock"
        assert body["mock"] is True
        assert body["image_base64"]
        assert body["mime_type"] == "image/png"
    finally:
        app.dependency_overrides.clear()


def test_room_preview_image_mock_is_not_metered(monkeypatch) -> None:
    """Mock images cost nothing, so they must not consume the monthly cap."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
    monkeypatch.setenv("API_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("ROOM_IMAGE_MONTHLY_CAP", "50")

    from api.auth import get_current_user
    from api.main import app
    from db import client as db_client

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "role": "owner",
    }
    client = TestClient(app)
    try:
        with (
            patch.object(db_client, "count_design_intent_usage", return_value=0),
            patch.object(db_client, "insert_design_intent_usage") as insert,
        ):
            resp = client.post(
                "/api/commerce/room-preview-image",
                json={"utterance": "sage green walls", "overlays": []},
            )
        assert resp.status_code == 200
        assert resp.json()["mock"] is True
        insert.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_room_preview_image_rejects_over_cap(monkeypatch) -> None:
    """Past the monthly cap the route must refuse before calling the provider."""
    monkeypatch.setenv("API_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("ROOM_IMAGE_MONTHLY_CAP", "50")

    from api.auth import get_current_user
    from api.main import app
    from db import client as db_client

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "role": "owner",
    }
    client = TestClient(app)
    try:
        with (
            patch.object(db_client, "count_design_intent_usage", return_value=50),
            patch("api.routes.commerce.generate_room_preview_image") as generate,
        ):
            resp = client.post(
                "/api/commerce/room-preview-image",
                json={"utterance": "sage green walls", "overlays": []},
            )
        assert resp.status_code == 429
        assert "50/50" in resp.json()["detail"]
        generate.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_room_preview_image_records_billed_generation(monkeypatch) -> None:
    """A real provider call must be recorded against the caller for the cap."""
    monkeypatch.setenv("API_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("ROOM_IMAGE_MONTHLY_CAP", "50")

    from api.auth import get_current_user
    from api.main import app
    from db import client as db_client

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "role": "owner",
    }
    client = TestClient(app)
    try:
        with (
            patch.object(db_client, "count_design_intent_usage", return_value=0),
            patch.object(db_client, "insert_design_intent_usage") as insert,
            patch(
                "api.routes.commerce.generate_room_preview_image",
                return_value={
                    "image_base64": "aGk=",
                    "mime_type": "image/png",
                    "provider": "openai",
                    "model": "gpt-image-1",
                    "prompt": "p",
                    "mock": False,
                },
            ),
        ):
            resp = client.post(
                "/api/commerce/room-preview-image",
                json={"utterance": "sage green walls", "overlays": []},
            )
        assert resp.status_code == 200
        insert.assert_called_once()
        kwargs = insert.call_args.kwargs
        assert kwargs["kind"] == "room_image"
        assert kwargs["model"] == "gpt-image-1"
        assert kwargs["room_scan_id"] is None
    finally:
        app.dependency_overrides.clear()
