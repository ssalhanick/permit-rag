"""Unit tests for scripts/purge_project_uploads.py helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.purge_project_uploads import (
    build_purge_request,
    load_doc_ids,
    resolve_admin_token,
)


def test_load_doc_ids_merges_file_and_args(tmp_path: Path) -> None:
    """load_doc_ids should merge, trim, and dedupe values."""
    path = tmp_path / "ids.txt"
    path.write_text("doc-a\n#comment\ndoc-b\ndoc-a\n", encoding="utf-8")
    result = load_doc_ids([" doc-c ", "doc-b"], str(path))
    assert result == ["doc-c", "doc-b", "doc-a"]


def test_resolve_admin_token_prefers_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI token should override env token."""
    monkeypatch.setenv("API_ADMIN_TOKEN", "env-token")
    assert resolve_admin_token("cli-token") == "cli-token"


def test_resolve_admin_token_raises_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing token should raise clear error."""
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        resolve_admin_token(None)


def test_build_purge_request_contains_headers() -> None:
    """Request should target purge endpoint with auth headers."""
    request = build_purge_request("http://localhost:8000/", "doc-1", "tkn", "admin", "alice")
    assert request.get_method() == "POST"
    assert request.full_url.endswith("/admin/documents/doc-1/purge-project-upload")
    assert request.headers["X-admin-token"] == "tkn"
    assert request.headers["X-admin-role"] == "admin"
    assert request.headers["X-admin-user"] == "alice"
