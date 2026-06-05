"""Unit tests for db.client purge audit insert helper."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from db import client as db_client


def test_insert_purge_audit_log_writes_expected_fields(monkeypatch) -> None:
    """insert_purge_audit_log should execute insert with expected params."""
    captured: dict = {"params": None, "committed": False}

    class _FakeResult:
        def fetchone(self):
            return {"id": uuid4(), "doc_id": "doc-1"}

    class _FakeConn:
        def execute(self, _sql: str, params: dict):
            captured["params"] = params
            return _FakeResult()

        def commit(self):
            captured["committed"] = True

    @contextmanager
    def _fake_get_conn():
        yield _FakeConn()

    monkeypatch.setattr(db_client, "get_conn", _fake_get_conn)
    row = db_client.insert_purge_audit_log(
        doc_id="doc-1",
        document_id=uuid4(),
        actor_identity="qa-user",
        actor_role="owner",
        source_tier=3,
        deleted_chunk_count=4,
        local_file_deleted=True,
    )

    assert row["doc_id"] == "doc-1"
    assert captured["committed"] is True
    assert captured["params"]["actor_identity"] == "qa-user"
    assert captured["params"]["actor_role"] == "owner"
    assert captured["params"]["source_tier"] == 3
    assert captured["params"]["deleted_chunk_count"] == 4
    assert captured["params"]["local_file_deleted"] is True
