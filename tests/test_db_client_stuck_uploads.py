"""Unit tests for db.client.get_stuck_draft_documents."""

from __future__ import annotations

from contextlib import contextmanager

from db import client as db_client


def _fake_conn(*, fetchall_result=None):
    captured: dict = {"sql": None, "params": None}

    class _FakeResult:
        def fetchall(self):
            return fetchall_result or []

    class _FakeConn:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return _FakeResult()

    @contextmanager
    def _factory():
        yield _FakeConn()

    return _factory, captured


def test_get_stuck_draft_documents_default_threshold(monkeypatch) -> None:
    factory, captured = _fake_conn(fetchall_result=[{"doc_id": "stuck-1", "chunk_count": 0}])
    monkeypatch.setattr(db_client, "get_conn", factory)

    rows = db_client.get_stuck_draft_documents()

    assert rows == [{"doc_id": "stuck-1", "chunk_count": 0}]
    assert captured["params"]["min_age_minutes"] == 30
    assert "document_status = 'draft'" in captured["sql"]
    assert "having count(c.id) = 0" in captured["sql"].lower()


def test_get_stuck_draft_documents_custom_threshold(monkeypatch) -> None:
    factory, captured = _fake_conn(fetchall_result=[])
    monkeypatch.setattr(db_client, "get_conn", factory)

    rows = db_client.get_stuck_draft_documents(min_age_minutes=90)

    assert rows == []
    assert captured["params"]["min_age_minutes"] == 90
