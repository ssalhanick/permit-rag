"""Unit tests for db.client.get_jurisdiction_chain."""

from __future__ import annotations

from contextlib import contextmanager

from db import client as db_client


def _fake_get_conn(rows: list[dict]):
    class _FakeResult:
        def fetchall(self):
            return rows

    class _FakeConn:
        def execute(self, _sql, params):
            captured["params"] = params
            return _FakeResult()

    @contextmanager
    def _factory():
        yield _FakeConn()

    return _factory


captured: dict = {}


def test_get_jurisdiction_chain_orders_local_to_federal(monkeypatch) -> None:
    """The chain should come back local -> county -> state -> federal, as ordered by the query."""
    rows = [
        {"id": "dallas"}, {"id": "dallas-county"}, {"id": "texas"}, {"id": "federal"},
    ]
    monkeypatch.setattr(db_client, "get_conn", _fake_get_conn(rows))

    chain = db_client.get_jurisdiction_chain("dallas")

    assert chain == ["dallas", "dallas-county", "texas", "federal"]
    assert captured["params"] == {"start": "dallas"}


def test_get_jurisdiction_chain_unknown_id_falls_back_to_itself(monkeypatch) -> None:
    """An id with no jurisdictions row should still filter by itself, not silently pass everything."""
    monkeypatch.setattr(db_client, "get_conn", _fake_get_conn([]))

    chain = db_client.get_jurisdiction_chain("frisco")

    assert chain == ["frisco"]
