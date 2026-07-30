"""Unit tests for db.client overlay petition/approval functions (migration 038)."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from db import client as db_client


def _fake_conn(*, fetchone_result=None, fetchall_result=None):
    captured: dict = {"sql": None, "params": None, "committed": False}

    class _FakeResult:
        def fetchone(self):
            return fetchone_result

        def fetchall(self):
            return fetchall_result or []

    class _FakeConn:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return _FakeResult()

        def commit(self):
            captured["committed"] = True

    @contextmanager
    def _factory():
        yield _FakeConn()

    return _factory, captured


def test_create_overlay_petition_writes_expected_fields(monkeypatch) -> None:
    overlay_id = uuid4()
    project_id = uuid4()
    user_id = uuid4()
    factory, captured = _fake_conn(
        fetchone_result={"id": overlay_id, "name": "Swiss Avenue Historic District", "status": "petitioned"}
    )
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.create_overlay_petition(
        name="Swiss Avenue Historic District",
        overlay_type="historic_district",
        jurisdiction_id="dallas",
        petitioned_by=user_id,
        petitioning_project_id=project_id,
        latitude=32.8, longitude=-96.78,
    )

    assert row["id"] == overlay_id
    assert captured["committed"] is True
    assert captured["params"]["name"] == "Swiss Avenue Historic District"
    assert captured["params"]["overlay_type"] == "historic_district"
    assert captured["params"]["petitioning_project_id"] == project_id
    assert captured["params"]["buffer_meters"] == 200.0


def test_approve_overlay_without_refined_geometry(monkeypatch) -> None:
    overlay_id = uuid4()
    approver_id = uuid4()
    factory, captured = _fake_conn(fetchone_result={"id": overlay_id, "status": "approved"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.approve_overlay(overlay_id, approved_by=approver_id)

    assert row["status"] == "approved"
    assert captured["params"]["approved_by"] == approver_id
    assert "geojson" not in captured["params"]


def test_approve_overlay_with_refined_geometry(monkeypatch) -> None:
    overlay_id = uuid4()
    approver_id = uuid4()
    geojson = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
    factory, captured = _fake_conn(fetchone_result={"id": overlay_id, "status": "approved"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.approve_overlay(overlay_id, approved_by=approver_id, geojson_polygon=geojson)

    assert captured["params"]["geojson"] == geojson
    assert "ST_GeomFromGeoJSON" in captured["sql"]


def test_reject_overlay(monkeypatch) -> None:
    overlay_id = uuid4()
    factory, captured = _fake_conn(fetchone_result={"id": overlay_id, "status": "rejected"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.reject_overlay(overlay_id, approved_by=None)

    assert row["status"] == "rejected"
    assert captured["params"]["approved_by"] is None


def test_list_pending_overlay_petitions(monkeypatch) -> None:
    factory, _ = _fake_conn(fetchall_result=[{"id": uuid4(), "status": "petitioned"}])
    monkeypatch.setattr(db_client, "get_conn", factory)

    rows = db_client.list_pending_overlay_petitions()

    assert len(rows) == 1
    assert rows[0]["status"] == "petitioned"


def test_match_overlay_chunks_filters_by_similarity(monkeypatch) -> None:
    factory, captured = _fake_conn(
        fetchall_result=[
            {"id": "c1", "similarity": 0.9},
            {"id": "c2", "similarity": 0.1},
        ]
    )
    monkeypatch.setattr(db_client, "get_conn", factory)

    rows = db_client.match_overlay_chunks(
        [0.1, 0.2], latitude=32.8, longitude=-96.78, top_k=5, min_similarity=0.5,
    )

    assert [r["id"] for r in rows] == ["c1"]
    assert captured["params"]["lat"] == 32.8
    assert captured["params"]["lng"] == -96.78
