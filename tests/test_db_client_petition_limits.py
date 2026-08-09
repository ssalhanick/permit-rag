"""Unit tests for db.client's contributor-submission dedup/rate-limit helpers."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from db import client as db_client


def _fake_conn(*, fetchone_result=None):
    captured: dict = {"sql": None, "params": None}

    class _FakeResult:
        def fetchone(self):
            return fetchone_result

    class _FakeConn:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return _FakeResult()

    @contextmanager
    def _factory():
        yield _FakeConn()

    return _factory, captured


def test_get_document_by_checksum_excludes_rejected(monkeypatch) -> None:
    factory, captured = _fake_conn(fetchone_result={"doc_id": "x", "checksum_sha256": "abc"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.get_document_by_checksum("abc")

    assert row["doc_id"] == "x"
    assert "checksum_sha256 = %s" in captured["sql"]
    assert "document_status != 'rejected'" in captured["sql"]
    assert captured["params"] == ("abc",)


def test_get_document_by_checksum_no_match(monkeypatch) -> None:
    factory, _ = _fake_conn(fetchone_result=None)
    monkeypatch.setattr(db_client, "get_conn", factory)

    assert db_client.get_document_by_checksum("no-such-hash") is None


def test_count_recent_documents_by_user_default_window(monkeypatch) -> None:
    user_id = uuid4()
    factory, captured = _fake_conn(fetchone_result={"n": 3})
    monkeypatch.setattr(db_client, "get_conn", factory)

    count = db_client.count_recent_documents_by_user(user_id)

    assert count == 3
    assert captured["params"]["user_id"] == user_id
    assert captured["params"]["minutes"] == 60


def test_count_recent_documents_by_user_no_rows_returns_zero(monkeypatch) -> None:
    factory, _ = _fake_conn(fetchone_result=None)
    monkeypatch.setattr(db_client, "get_conn", factory)

    assert db_client.count_recent_documents_by_user(uuid4()) == 0
