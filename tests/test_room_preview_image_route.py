"""tests/test_room_preview_image_route.py — commerce room image API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_room_preview_image_returns_mock_without_openai(monkeypatch) -> None:
    """Route should return mock PNG payload when keys are absent."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
    monkeypatch.setenv("API_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "false")

    from api.main import app
    from api.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000001",
        "role": "owner",
    }
    client = TestClient(app)
    try:
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
