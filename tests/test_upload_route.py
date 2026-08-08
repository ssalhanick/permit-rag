"""
tests/test_upload_route.py — regression tests for upload background flow
=======================================================================
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.routes import upload as upload_route


def _stub_validate_document(**overrides):
    """A no-op metadata-proposal stub — most tests don't care about this step,
    just that it doesn't make a real (slow, DB-backed) call."""
    defaults = {"result": "pass", "proposals": []}
    defaults.update(overrides)
    return lambda *_a, **_k: SimpleNamespace(**defaults)


def _write_dummy_file(path: str) -> None:
    """Create a tiny local file for checksum path."""
    with open(path, "wb") as file_obj:
        file_obj.write(b"dummy upload bytes")


def test_process_upload_success_runs_chunk_insert_embed(monkeypatch, tmp_path) -> None:
    """Background upload should chunk, store, embed, then activate document."""
    local_file = tmp_path / "sample.pdf"
    _write_dummy_file(str(local_file))
    calls: dict[str, object] = {}

    monkeypatch.setattr(upload_route, "insert_document", lambda **kwargs: {"id": uuid4(), **kwargs})
    monkeypatch.setattr(upload_route, "chunk_document", lambda doc_id: {"chunks": [{"chunk_index": 0, "content": "x", "char_count": 1}]})
    monkeypatch.setattr(upload_route, "delete_chunks_for_document", lambda _doc_uuid: 0)
    monkeypatch.setattr(upload_route, "insert_chunks", lambda _doc_uuid, chunks: len(chunks))
    monkeypatch.setattr(upload_route, "embed_document", lambda _doc_id, force: {"num_new": 1})
    monkeypatch.setattr(upload_route, "validate_document", _stub_validate_document())
    monkeypatch.setattr(
        upload_route,
        "update_document_admin_fields",
        lambda doc_id, **kwargs: calls.update({"doc_id": doc_id, "status": kwargs.get("document_status")}),
    )

    upload_route._process_upload(
        doc_id="test-doc",
        local_path=str(local_file),
        source_url="file://dummy",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=["test"],
        source_tier=2,
    )

    assert calls["doc_id"] == "test-doc"
    assert calls["status"] == "active"


def test_process_upload_failure_marks_needs_ocr(monkeypatch, tmp_path) -> None:
    """Background upload should downgrade status when chunk/embed fails."""
    local_file = tmp_path / "sample.pdf"
    _write_dummy_file(str(local_file))
    calls: dict[str, str] = {}

    monkeypatch.setattr(upload_route, "insert_document", lambda **kwargs: {"id": uuid4(), **kwargs})

    def _boom(_doc_id: str) -> dict:
        raise RuntimeError("chunk failure")

    monkeypatch.setattr(upload_route, "chunk_document", _boom)
    monkeypatch.setattr(
        upload_route,
        "update_document_admin_fields",
        lambda doc_id, **kwargs: calls.update({"doc_id": doc_id, "status": kwargs.get("document_status", "")}),
    )

    upload_route._process_upload(
        doc_id="bad-doc",
        local_path=str(local_file),
        source_url="file://dummy",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=[],
        source_tier=2,
    )

    assert calls["doc_id"] == "bad-doc"
    assert calls["status"] == "needs_ocr"


def test_process_upload_html_failure_stays_draft(monkeypatch, tmp_path) -> None:
    """HTML failure should remain draft (needs_ocr is PDF-only)."""
    local_file = tmp_path / "sample.html"
    _write_dummy_file(str(local_file))
    calls: dict[str, str] = {}

    monkeypatch.setattr(upload_route, "insert_document", lambda **kwargs: {"id": uuid4(), **kwargs})
    monkeypatch.setattr(upload_route, "chunk_document", lambda _doc_id: {"chunks": []})
    monkeypatch.setattr(
        upload_route,
        "update_document_admin_fields",
        lambda doc_id, **kwargs: calls.update({"doc_id": doc_id, "status": kwargs.get("document_status", "")}),
    )

    upload_route._process_upload(
        doc_id="bad-html",
        local_path=str(local_file),
        source_url="file://dummy",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=[],
        source_tier=2,
    )

    assert calls["doc_id"] == "bad-html"
    assert calls["status"] == "draft"


def test_process_upload_html_retries_without_filter(monkeypatch, tmp_path) -> None:
    """HTML with empty filtered result should retry and activate on second pass."""
    local_file = tmp_path / "retry.html"
    _write_dummy_file(str(local_file))
    calls: dict[str, object] = {"chunk_calls": 0}

    monkeypatch.setattr(upload_route, "insert_document", lambda **kwargs: {"id": uuid4(), **kwargs})

    def _chunk(_doc_id: str) -> dict:
        calls["chunk_calls"] = int(calls["chunk_calls"]) + 1
        if calls["chunk_calls"] == 1:
            return {"chunks": []}
        return {"chunks": [{"chunk_index": 0, "content": "x", "char_count": 1}]}

    monkeypatch.setattr(upload_route, "chunk_document", _chunk)
    monkeypatch.setattr(upload_route, "delete_chunks_for_document", lambda _doc_uuid: 0)
    monkeypatch.setattr(upload_route, "insert_chunks", lambda _doc_uuid, chunks: len(chunks))
    monkeypatch.setattr(upload_route, "embed_document", lambda _doc_id, force: {"num_new": 1})
    monkeypatch.setattr(upload_route, "validate_document", _stub_validate_document())
    monkeypatch.setattr(
        upload_route,
        "update_document_admin_fields",
        lambda doc_id, **kwargs: calls.update({"doc_id": doc_id, "status": kwargs.get("document_status")}),
    )

    upload_route._process_upload(
        doc_id="retry-html",
        local_path=str(local_file),
        source_url="file://dummy",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=[],
        source_tier=2,
    )

    assert calls["chunk_calls"] == 2
    assert calls["status"] == "active"


# ═══════════════════════════════════════════════════════════════
#  _propose_metadata — post-upload subject_tags/effective_date review queue
# ═══════════════════════════════════════════════════════════════


def test_process_upload_calls_validate_document_on_success(monkeypatch, tmp_path) -> None:
    """The one shared metadata-proposal LLM pass runs after a successful
    upload, over the doc_id that was just chunked/embedded."""
    local_file = tmp_path / "sample.pdf"
    _write_dummy_file(str(local_file))
    calls: dict[str, object] = {}

    monkeypatch.setattr(upload_route, "insert_document", lambda **kwargs: {"id": uuid4(), **kwargs})
    monkeypatch.setattr(upload_route, "chunk_document", lambda doc_id: {"chunks": [{"chunk_index": 0, "content": "x", "char_count": 1}]})
    monkeypatch.setattr(upload_route, "delete_chunks_for_document", lambda _doc_uuid: 0)
    monkeypatch.setattr(upload_route, "insert_chunks", lambda _doc_uuid, chunks: len(chunks))
    monkeypatch.setattr(upload_route, "embed_document", lambda _doc_id, force: {"num_new": 1})
    monkeypatch.setattr(upload_route, "update_document_admin_fields", lambda doc_id, **kwargs: None)

    def _validate(doc_id, **kwargs):
        calls["doc_id"] = doc_id
        calls["kwargs"] = kwargs
        return SimpleNamespace(result="needs_review", proposals=["subject_tags", "effective_date"])

    monkeypatch.setattr(upload_route, "validate_document", _validate)

    upload_route._process_upload(
        doc_id="tagged-doc",
        local_path=str(local_file),
        source_url="file://dummy",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=[],
        source_tier=2,
    )

    assert calls["doc_id"] == "tagged-doc"
    # draft_on_fail=False: today's immediate-activation behavior stays
    # unaffected by this — it only adds needs_review proposals on top.
    assert calls["kwargs"]["draft_on_fail"] is False
    assert calls["kwargs"]["file_action_items"] is True


def test_process_upload_survives_metadata_proposal_failure(monkeypatch, tmp_path) -> None:
    """A metadata-proposal failure is best-effort — it must not undo an
    otherwise-successful upload (document still ends up 'active')."""
    local_file = tmp_path / "sample.pdf"
    _write_dummy_file(str(local_file))
    calls: dict[str, object] = {}

    monkeypatch.setattr(upload_route, "insert_document", lambda **kwargs: {"id": uuid4(), **kwargs})
    monkeypatch.setattr(upload_route, "chunk_document", lambda doc_id: {"chunks": [{"chunk_index": 0, "content": "x", "char_count": 1}]})
    monkeypatch.setattr(upload_route, "delete_chunks_for_document", lambda _doc_uuid: 0)
    monkeypatch.setattr(upload_route, "insert_chunks", lambda _doc_uuid, chunks: len(chunks))
    monkeypatch.setattr(upload_route, "embed_document", lambda _doc_id, force: {"num_new": 1})

    def _boom(*_a, **_k):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(upload_route, "validate_document", _boom)
    monkeypatch.setattr(
        upload_route,
        "update_document_admin_fields",
        lambda doc_id, **kwargs: calls.update({"doc_id": doc_id, "status": kwargs.get("document_status")}),
    )

    upload_route._process_upload(
        doc_id="test-doc",
        local_path=str(local_file),
        source_url="file://dummy",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=["test"],
        source_tier=2,
    )

    assert calls["status"] == "active"


# ═══════════════════════════════════════════════════════════════
#  _require_admin_or_jwt — regression: role must be 'admin'
# ═══════════════════════════════════════════════════════════════


def test_require_admin_or_jwt_rejects_non_admin_authenticated_user(monkeypatch) -> None:
    """
    A logged-in Cognito user with role='member' must NOT bypass the admin
    gate. Previously any truthy current_user was accepted regardless of
    role, letting any authenticated (non-admin) account upload documents.
    """
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)

    member_user = {"user_id": uuid4(), "role": "member", "username": "regular-user"}

    with pytest.raises(HTTPException) as exc_info:
        upload_route._require_admin_or_jwt(token=None, current_user=member_user)
    assert exc_info.value.status_code == 401


def test_require_admin_or_jwt_allows_cognito_admin(monkeypatch) -> None:
    """A logged-in Cognito user with role='admin' satisfies the admin gate."""
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.delenv("API_ADMIN_TOKEN", raising=False)

    admin_user = {"user_id": uuid4(), "role": "admin", "username": "site-owner"}

    result = upload_route._require_admin_or_jwt(token=None, current_user=admin_user)
    assert result == admin_user


def test_require_admin_or_jwt_allows_shared_token(monkeypatch) -> None:
    """The shared X-Admin-Token path still works (machine credential for scripts)."""
    monkeypatch.setenv("API_ADMIN_AUTH_REQUIRED", "true")
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-token")

    result = upload_route._require_admin_or_jwt(token="secret-token", current_user=None)
    assert result["role"] == "admin"
