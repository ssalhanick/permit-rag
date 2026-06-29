"""
tests/test_api_main.py — API app-level behavior tests
=====================================================
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import _parse_cors_origins, app


def test_parse_cors_origins_uses_default_local_allowlist(monkeypatch) -> None:
    """CORS parser should return local dev defaults when env is unset."""
    monkeypatch.delenv("API_CORS_ALLOW_ALL", raising=False)
    monkeypatch.delenv("API_CORS_ALLOW_ORIGINS", raising=False)
    origins = _parse_cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://localhost:5173" in origins
    assert "http://localhost:5175" in origins


def test_parse_cors_origins_reads_csv_from_env(monkeypatch) -> None:
    """CORS parser should split and trim comma-separated origins."""
    monkeypatch.setenv("API_CORS_ALLOW_ALL", "false")
    monkeypatch.setenv(
        "API_CORS_ALLOW_ORIGINS",
        " https://app.example.com , https://admin.example.com ",
    )
    assert _parse_cors_origins() == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_parse_cors_origins_allow_all_override(monkeypatch) -> None:
    """CORS parser should allow wildcard when explicit override is enabled."""
    monkeypatch.setenv("API_CORS_ALLOW_ALL", "true")
    monkeypatch.setenv("API_CORS_ALLOW_ORIGINS", "https://ignored.example.com")
    assert _parse_cors_origins() == ["*"]


def test_validation_error_handler_returns_string_detail() -> None:
    """Validation errors should use compact string detail payloads."""
    client = TestClient(app)
    response = client.get("/documents", params={"authority": "city"})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body.get("detail"), str)
    assert body["detail"].startswith("Validation error")


def test_http_exception_handler_returns_string_detail(monkeypatch) -> None:
    """HTTPException payloads should normalize detail to a string."""
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    client = TestClient(app)
    response = client.patch("/admin/documents/demo-doc", json={})
    assert response.status_code == 503
    body = response.json()
    assert isinstance(body.get("detail"), str)
    assert "API_ADMIN_TOKEN" in body["detail"]
