"""
tests/test_governance.py — Unit tests for ingestion/governance.py (Sprint 3 / Task 9)

Tests cover:
    - sha256_bytes helper
    - check_document_changed (no_change, new_document, changed)
    - run_supersession_flow (success, old doc missing, same id error)
    - rescrape_document (no_change, new_document, changed+rechunk=False)

All DB interactions are mocked via unittest.mock.patch so no live DB is needed.
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from ingestion.governance import (
    ChangeStatus,
    RescrapeResult,
    check_document_changed,
    rescrape_document,
    run_supersession_flow,
    sha256_bytes,
)


# ════════════════════════════════════════════════
#  sha256_bytes
# ════════════════════════════════════════════════


def test_sha256_bytes_returns_64_char_hex():
    result = sha256_bytes(b"hello world")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


def test_sha256_bytes_matches_hashlib():
    data = b"permit_rag test data"
    expected = hashlib.sha256(data).hexdigest()
    assert sha256_bytes(data) == expected


def test_sha256_bytes_different_inputs_differ():
    assert sha256_bytes(b"foo") != sha256_bytes(b"bar")


# ════════════════════════════════════════════════
#  check_document_changed
# ════════════════════════════════════════════════


@patch("db.client.get_document_by_doc_id", return_value=None)
def test_check_new_document(mock_get):
    status, stored = check_document_changed("new-doc", "abc123")
    assert status == ChangeStatus.NEW_DOCUMENT
    assert stored is None
    mock_get.assert_called_once_with("new-doc")


@patch(
    "db.client.get_document_by_doc_id",
    return_value={"checksum_sha256": "aabbcc"},
)
def test_check_no_change(mock_get):
    status, stored = check_document_changed("existing-doc", "aabbcc")
    assert status == ChangeStatus.NO_CHANGE
    assert stored == "aabbcc"


@patch(
    "db.client.get_document_by_doc_id",
    return_value={"checksum_sha256": "oldoldold"},
)
def test_check_changed(mock_get):
    status, stored = check_document_changed("existing-doc", "newnewnew")
    assert status == ChangeStatus.CHANGED
    assert stored == "oldoldold"


@patch(
    "db.client.get_document_by_doc_id",
    return_value={"checksum_sha256": None},
)
def test_check_missing_stored_hash_treated_as_new(mock_get):
    """A doc row with no stored hash should be treated as NEW (re-ingest)."""
    status, stored = check_document_changed("partial-doc", "anyhash")
    assert status == ChangeStatus.NEW_DOCUMENT


# ════════════════════════════════════════════════
#  run_supersession_flow
# ════════════════════════════════════════════════


@patch("db.client.supersede_document")
def test_run_supersession_ok(mock_supersede):
    mock_supersede.return_value = {
        "doc_id": "old-doc",
        "document_status": "superseded",
        "is_current": False,
        "retrieval_weight": 0.1,
    }
    result = run_supersession_flow("old-doc", "new-doc")
    assert result["document_status"] == "superseded"
    mock_supersede.assert_called_once_with("old-doc", "new-doc", superseded_weight=0.1)


@patch("db.client.supersede_document", return_value=None)
def test_run_supersession_raises_when_not_found(mock_supersede):
    with pytest.raises(RuntimeError, match="old_doc_id="):
        run_supersession_flow("ghost-doc", "new-doc")


# ════════════════════════════════════════════════
#  rescrape_document — no_change
# ════════════════════════════════════════════════


@patch("ingestion.governance.check_document_changed")
def test_rescrape_no_change(mock_check, tmp_path):
    content = b"unchanged pdf bytes"
    doc_hash = sha256_bytes(content)
    mock_check.return_value = (ChangeStatus.NO_CHANGE, doc_hash)

    raw_file = tmp_path / "doc.pdf"
    raw_file.write_bytes(content)

    catalog = {
        "url": "https://example.com/doc.pdf",
        "municipality": "dallas",
        "authority_level": "municipal",
        "doc_type": "building_code",
    }
    result = rescrape_document("test-doc", catalog, raw_file, content, rechunk=False)

    assert result.status == ChangeStatus.NO_CHANGE
    assert result.ok()
    assert result.superseded is False


# ════════════════════════════════════════════════
#  rescrape_document — new_document
# ════════════════════════════════════════════════


@patch("ingestion.governance.check_document_changed")
@patch("db.client.insert_document")
def test_rescrape_new_document(mock_insert, mock_check, tmp_path):
    import uuid
    content = b"brand new doc"
    mock_check.return_value = (ChangeStatus.NEW_DOCUMENT, None)
    mock_insert.return_value = {"id": uuid.uuid4(), "doc_id": "new-test-doc"}

    raw_file = tmp_path / "doc.pdf"
    raw_file.write_bytes(content)

    catalog = {
        "url": "https://example.com/doc.pdf",
        "municipality": "plano",
        "authority_level": "municipal",
        "doc_type": "permit_checklist",
    }
    result = rescrape_document("new-test-doc", catalog, raw_file, content, rechunk=False)

    assert result.status == ChangeStatus.NEW_DOCUMENT
    assert result.ok()
    assert result.superseded is False
    mock_insert.assert_called_once()


# ════════════════════════════════════════════════
#  rescrape_document — changed (no rechunk)
# ════════════════════════════════════════════════


@patch("ingestion.governance.check_document_changed")
@patch("db.client.insert_document")
@patch("db.client.get_document_by_doc_id")
@patch("ingestion.governance.run_supersession_flow")
def test_rescrape_changed_supersession(
    mock_supersede, mock_get_doc, mock_insert, mock_check, tmp_path
):
    import uuid
    content = b"updated pdf content"
    old_hash = sha256_bytes(b"old pdf content")

    mock_check.return_value = (ChangeStatus.CHANGED, old_hash)
    new_uuid = uuid.uuid4()
    mock_insert.return_value = {"id": new_uuid, "doc_id": "changed-doc-20260604"}
    mock_get_doc.return_value = {"doc_id": "changed-doc", "id": uuid.uuid4()}
    mock_supersede.return_value = {"document_status": "superseded"}

    raw_file = tmp_path / "doc.pdf"
    raw_file.write_bytes(content)

    catalog = {
        "url": "https://example.com/doc.pdf",
        "municipality": "dallas",
        "authority_level": "municipal",
        "doc_type": "zoning_ordinance",
    }
    result = rescrape_document("changed-doc", catalog, raw_file, content, rechunk=False)

    assert result.status == ChangeStatus.CHANGED
    assert result.ok()
    assert result.superseded is True
    mock_supersede.assert_called_once()
    assert "changed-doc" in result.new_doc_id  # versioned new id
