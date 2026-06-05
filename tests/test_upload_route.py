"""
tests/test_upload_route.py — regression tests for upload background flow
=======================================================================
"""

from __future__ import annotations

from uuid import uuid4

from api.routes import upload as upload_route


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
