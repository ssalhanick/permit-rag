"""
tests/test_governance_metadata.py — Phase 3 governance write path
=================================================================
apply_metadata_correction is the single corpus writer for corrected metadata;
flag_document_for_review is the draft-plus-blocking-item path. Both mocked.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from ingestion import governance


def test_apply_metadata_correction_writes_via_db(monkeypatch) -> None:
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: {"doc_id": _id})
    captured: dict = {}

    def _update(doc_id, **kwargs):
        captured.update({"doc_id": doc_id, **kwargs})
        return {"doc_id": doc_id, **kwargs}

    monkeypatch.setattr(db_client, "update_document_metadata_fields", _update)

    out = governance.apply_metadata_correction(
        "dallas-building-code",
        effective_date=date(2019, 6, 15),
        doc_type="zoning_ordinance",
        subject_tags=["zoning"],
        actor="uid-1",
    )
    assert captured["effective_date"] == date(2019, 6, 15)
    assert captured["doc_type"] == "zoning_ordinance"
    assert out["doc_id"] == "dallas-building-code"


def test_apply_metadata_correction_missing_doc_raises(monkeypatch) -> None:
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: None)
    with pytest.raises(RuntimeError):
        governance.apply_metadata_correction("ghost", doc_type="other")


def test_flag_document_drafts_and_files_item(monkeypatch) -> None:
    from db import client as db_client

    admin: dict = {}
    monkeypatch.setattr(db_client, "update_document_admin_fields",
                        lambda doc_id, **k: admin.update({"doc_id": doc_id, **k}))
    item = {"id": uuid4()}
    monkeypatch.setattr(db_client, "upsert_action_item", lambda **k: item)

    out = governance.flag_document_for_review(
        "new-doc", kind="metadata_incomplete", title="incomplete", set_draft=True,
    )
    assert admin["document_status"] == "draft"
    assert out["id"] == item["id"]


def test_flag_document_backfill_does_not_draft(monkeypatch) -> None:
    from db import client as db_client

    called = {"admin": False}

    def _admin(*a, **k):
        called["admin"] = True

    monkeypatch.setattr(db_client, "update_document_admin_fields", _admin)
    monkeypatch.setattr(db_client, "upsert_action_item", lambda **k: {"id": uuid4()})

    governance.flag_document_for_review(
        "live-doc", kind="metadata_needs_review", title="review", set_draft=False,
    )
    assert called["admin"] is False  # a live corpus doc is never drafted on backfill
