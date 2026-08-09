"""Unit tests for scripts/reconcile_stuck_uploads.py."""

from __future__ import annotations

from uuid import uuid4

from scripts.reconcile_stuck_uploads import _retry


def _stuck_row(**overrides):
    row = {
        "doc_id": "ordinance-petition-abc123",
        "local_path": "documents/raw/ordinance-petition-abc123.pdf",
        "source_url": "file:///documents/raw/ordinance-petition-abc123.pdf",
        "municipality": "plano",
        "authority_level": "municipal",
        "doc_type": "zoning_ordinance",
        "subject_tags": [],
        "source_tier": 2,
        "project_id": None,
        "uploaded_by": uuid4(),
        "overlay_id": None,
        "visibility": "team",
        "ingested_at": "2026-08-01T00:00:00Z",
        "chunk_count": 0,
    }
    row.update(overrides)
    return row


def test_retry_keeps_tier2_petitions_at_draft(monkeypatch) -> None:
    """A tier-2 ordinance petition must stay pending review on a successful
    retry, not skip the queue just because it happened to crash once."""
    calls = []
    monkeypatch.setattr(
        "api.routes.upload._process_upload",
        lambda **kwargs: calls.append(kwargs),
    )

    _retry([_stuck_row(source_tier=2)])

    assert len(calls) == 1
    assert calls[0]["auto_activate"] is False


def test_retry_keeps_overlay_documents_at_draft(monkeypatch) -> None:
    """A tier-3 document linked to an overlay petition must also stay
    'draft' pending overlay approval, not auto-activate on retry."""
    calls = []
    monkeypatch.setattr(
        "api.routes.upload._process_upload",
        lambda **kwargs: calls.append(kwargs),
    )
    overlay_id = uuid4()

    _retry([_stuck_row(source_tier=3, overlay_id=overlay_id)])

    assert len(calls) == 1
    assert calls[0]["auto_activate"] is False
    assert calls[0]["overlay_id"] == overlay_id


def test_retry_activates_ordinary_tier1_and_tier3_documents(monkeypatch) -> None:
    """A verified-contributor petition (tier 1) or a plain project document
    (tier 3, no overlay) was never meant to be review-gated -- retry should
    restore that behavior, not silently strand it at 'draft' forever."""
    calls = []
    monkeypatch.setattr(
        "api.routes.upload._process_upload",
        lambda **kwargs: calls.append(kwargs),
    )

    _retry([_stuck_row(source_tier=1, overlay_id=None), _stuck_row(source_tier=3, overlay_id=None)])

    assert len(calls) == 2
    assert all(c["auto_activate"] is True for c in calls)


def test_retry_continues_after_one_row_raises(monkeypatch) -> None:
    """One row failing unexpectedly (e.g. its local_path is gone) must not
    stop the rest of the batch from being retried."""
    calls = []

    def _fake_process_upload(**kwargs):
        if kwargs["doc_id"] == "boom":
            raise FileNotFoundError("gone")
        calls.append(kwargs["doc_id"])

    monkeypatch.setattr("api.routes.upload._process_upload", _fake_process_upload)

    _retry([_stuck_row(doc_id="boom"), _stuck_row(doc_id="fine")])

    assert calls == ["fine"]
