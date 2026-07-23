"""Unit tests for db.client project delete/restore audit insert helper."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from db import client as db_client


def test_insert_project_delete_audit_log_writes_expected_fields(monkeypatch) -> None:
    """insert_project_delete_audit_log should execute insert with expected params."""
    captured: dict = {"params": None, "committed": False}

    class _FakeResult:
        def fetchone(self):
            return {"id": uuid4(), "project_name": "Kitchen Remodel"}

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
    project_id = uuid4()
    owner_id = uuid4()
    actor_id = uuid4()
    row = db_client.insert_project_delete_audit_log(
        project_id=project_id,
        project_name="Kitchen Remodel",
        owner_user_id=owner_id,
        actor_user_id=actor_id,
        actor_username="qa-superadmin",
        actor_role="superadmin",
        action="hard_delete",
    )

    assert row["project_name"] == "Kitchen Remodel"
    assert captured["committed"] is True
    assert captured["params"]["project_id"] == project_id
    assert captured["params"]["owner_user_id"] == owner_id
    assert captured["params"]["actor_user_id"] == actor_id
    assert captured["params"]["actor_username"] == "qa-superadmin"
    assert captured["params"]["actor_role"] == "superadmin"
    assert captured["params"]["action"] == "hard_delete"
