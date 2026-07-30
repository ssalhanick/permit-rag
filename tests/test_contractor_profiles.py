"""
tests/test_contractor_profiles.py — db.client contractor profile/license helpers.

Same fake-connection pattern as test_db_client_project_delete_audit.py: no real
Postgres connection, just a monkeypatched get_conn() that captures the SQL/params
each call would have sent and lets fetchone/fetchall/rowcount be scripted.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from uuid import uuid4

from db import client as db_client


class _FakeResult:
    def __init__(self, one=None, many=None, rowcount=0):
        self._one = one
        self._many = many if many is not None else []
        self.rowcount = rowcount

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class _FakeConn:
    def __init__(self, *, one=None, many=None, rowcount=0):
        self.calls = []
        self.committed = False
        self._one = one
        self._many = many
        self._rowcount = rowcount

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _FakeResult(one=self._one, many=self._many, rowcount=self._rowcount)

    def commit(self):
        self.committed = True


def _patch_conn(monkeypatch, conn):
    @contextmanager
    def _fake_get_conn():
        yield conn

    monkeypatch.setattr(db_client, "get_conn", _fake_get_conn)


# ── contractor_profiles ──────────────────────────────────────────


def test_create_contractor_profile_inserts_and_commits(monkeypatch) -> None:
    user_id = uuid4()
    returned = {"id": uuid4(), "user_id": user_id, "business_name": "Acme Roofing"}
    conn = _FakeConn(one=returned)
    _patch_conn(monkeypatch, conn)

    row = db_client.create_contractor_profile(user_id=user_id, business_name="Acme Roofing", trades=["Roofing"])

    assert row == returned
    assert conn.committed is True
    _, params = conn.calls[0]
    assert params["user_id"] == user_id
    assert params["business_name"] == "Acme Roofing"
    assert params["trades"] == ["Roofing"]


def test_create_contractor_profile_defaults_empty_arrays(monkeypatch) -> None:
    conn = _FakeConn(one={"id": uuid4()})
    _patch_conn(monkeypatch, conn)

    db_client.create_contractor_profile(user_id=uuid4(), business_name="Acme")

    _, params = conn.calls[0]
    assert params["trades"] == []
    assert params["service_municipalities"] == []


def test_contractor_profile_exists_true_when_row_found(monkeypatch) -> None:
    conn = _FakeConn(one={"exists": 1})
    _patch_conn(monkeypatch, conn)
    assert db_client.contractor_profile_exists(uuid4()) is True


def test_contractor_profile_exists_false_when_no_row(monkeypatch) -> None:
    conn = _FakeConn(one=None)
    _patch_conn(monkeypatch, conn)
    assert db_client.contractor_profile_exists(uuid4()) is False


def test_update_contractor_profile_only_sets_provided_fields(monkeypatch) -> None:
    user_id = uuid4()
    conn = _FakeConn(one={"id": uuid4(), "business_name": "New Name"})
    _patch_conn(monkeypatch, conn)

    db_client.update_contractor_profile(user_id, business_name="New Name")

    sql, params = conn.calls[0]
    assert "business_name = %(business_name)s" in sql
    assert "phone" not in sql
    assert params["business_name"] == "New Name"
    assert conn.committed is True


def test_update_contractor_profile_no_fields_short_circuits_to_get(monkeypatch) -> None:
    user_id = uuid4()
    existing = {"id": uuid4(), "user_id": user_id}
    conn = _FakeConn(one=existing)
    _patch_conn(monkeypatch, conn)

    row = db_client.update_contractor_profile(user_id)

    assert row == existing
    assert conn.committed is False  # falls through to a plain SELECT, no UPDATE/commit


# ── contractor_licenses ──────────────────────────────────────────


def test_create_contractor_license_inserts_all_fields(monkeypatch) -> None:
    profile_id = uuid4()
    returned = {"id": uuid4(), "contractor_profile_id": profile_id}
    conn = _FakeConn(one=returned)
    _patch_conn(monkeypatch, conn)

    row = db_client.create_contractor_license(
        contractor_profile_id=profile_id,
        trade="Electrical",
        license_number="TX12345",
        expiration_date=date(2027, 1, 1),
    )

    assert row == returned
    assert conn.committed is True
    _, params = conn.calls[0]
    assert params["trade"] == "Electrical"
    assert params["license_number"] == "TX12345"
    assert params["contractor_profile_id"] == profile_id


def test_list_contractor_licenses_returns_all_rows(monkeypatch) -> None:
    rows = [{"id": uuid4()}, {"id": uuid4()}]
    conn = _FakeConn(many=rows)
    _patch_conn(monkeypatch, conn)

    assert db_client.list_contractor_licenses(uuid4()) == rows


def test_update_contractor_license_partial_update(monkeypatch) -> None:
    license_id = uuid4()
    conn = _FakeConn(one={"id": license_id, "expiration_date": "2028-01-01"})
    _patch_conn(monkeypatch, conn)

    db_client.update_contractor_license(license_id, expiration_date=date(2028, 1, 1))

    sql, params = conn.calls[0]
    assert "expiration_date = %(expiration_date)s" in sql
    assert "trade = " not in sql
    assert conn.committed is True


def test_delete_contractor_license_returns_true_when_deleted(monkeypatch) -> None:
    conn = _FakeConn(rowcount=1)
    _patch_conn(monkeypatch, conn)
    assert db_client.delete_contractor_license(uuid4()) is True


def test_delete_contractor_license_returns_false_when_missing(monkeypatch) -> None:
    conn = _FakeConn(rowcount=0)
    _patch_conn(monkeypatch, conn)
    assert db_client.delete_contractor_license(uuid4()) is False


def test_has_valid_license_true_when_non_expired_found(monkeypatch) -> None:
    conn = _FakeConn(one={"exists": 1})
    _patch_conn(monkeypatch, conn)
    assert db_client.has_valid_license(uuid4()) is True


def test_has_valid_license_false_when_none_found(monkeypatch) -> None:
    conn = _FakeConn(one=None)
    _patch_conn(monkeypatch, conn)
    assert db_client.has_valid_license(uuid4()) is False
