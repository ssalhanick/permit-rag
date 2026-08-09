"""Unit tests for db.client overlay petition/approval functions (migration 038)."""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from db import client as db_client


def _fake_conn(*, fetchone_result=None, fetchall_result=None, fetchone_results=None):
    """``fetchone_results``, if given, is a list consumed one value per
    ``execute()`` call (for tests exercising code paths that issue more than
    one statement); otherwise every call returns ``fetchone_result``.

    ``captured["calls"]`` records every (sql, params) pair in order.
    ``captured["sql"]``/``["params"]`` alias the *last* call for tests that
    only issue one statement and don't care about call order.
    """
    captured: dict = {"sql": None, "params": None, "calls": [], "committed": False}
    remaining = list(fetchone_results) if fetchone_results is not None else None

    class _FakeResult:
        def __init__(self, value):
            self._value = value

        def fetchone(self):
            return self._value

        def fetchall(self):
            return fetchall_result or []

    class _FakeConn:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            captured["calls"].append({"sql": sql, "params": params})
            value = remaining.pop(0) if remaining is not None else fetchone_result
            return _FakeResult(value)

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
    assert captured["calls"][0]["params"]["approved_by"] == approver_id
    assert "geojson" not in captured["calls"][0]["params"]


def test_approve_overlay_with_refined_geometry(monkeypatch) -> None:
    overlay_id = uuid4()
    approver_id = uuid4()
    geojson = '{"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,0]]]}'
    factory, captured = _fake_conn(fetchone_result={"id": overlay_id, "status": "approved"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.approve_overlay(overlay_id, approved_by=approver_id, geojson_polygon=geojson)

    assert captured["calls"][0]["params"]["geojson"] == geojson
    assert "ST_GeomFromGeoJSON" in captured["calls"][0]["sql"]


def test_approve_overlay_activates_linked_document(monkeypatch) -> None:
    """The document created by petition_overlay is scheduled with
    auto_activate=False and sits at 'draft' -- approval must be what flips it
    to 'active', or an approved overlay's document stays invisible forever."""
    overlay_id = uuid4()
    approver_id = uuid4()
    factory, captured = _fake_conn(fetchone_result={"id": overlay_id, "status": "approved"})
    monkeypatch.setattr(db_client, "get_conn", factory)

    db_client.approve_overlay(overlay_id, approved_by=approver_id)

    assert len(captured["calls"]) == 2
    activate_call = captured["calls"][1]
    assert "UPDATE documents" in activate_call["sql"]
    assert "document_status = 'active'" in activate_call["sql"]
    assert "document_status = 'draft'" in activate_call["sql"]
    assert activate_call["params"]["overlay_id"] == overlay_id


def test_approve_overlay_skips_document_activation_when_overlay_missing(monkeypatch) -> None:
    """No overlay row found -> no document update should be attempted."""
    overlay_id = uuid4()
    factory, captured = _fake_conn(fetchone_result=None)
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.approve_overlay(overlay_id, approved_by=None)

    assert row is None
    assert len(captured["calls"]) == 1


def test_reject_overlay(monkeypatch) -> None:
    overlay_id = uuid4()
    # calls: UPDATE overlays -> SELECT linked draft document (none found)
    factory, captured = _fake_conn(
        fetchone_results=[{"id": overlay_id, "status": "rejected"}, None],
    )
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.reject_overlay(overlay_id, approved_by=None)

    assert row["status"] == "rejected"
    assert captured["calls"][0]["params"]["approved_by"] is None
    assert len(captured["calls"]) == 2  # no draft document found -> no delete


def test_reject_overlay_deletes_linked_draft_document(monkeypatch) -> None:
    """A rejected overlay must not leave its (still-'draft') source document
    orphaned in the DB -- reject_overlay should clean it up the same way
    reject_pending_document does for tier-2 ordinance petitions."""
    overlay_id = uuid4()
    document_id = uuid4()
    factory, captured = _fake_conn(
        fetchone_results=[
            {"id": overlay_id, "status": "rejected"},  # UPDATE overlays
            {"id": document_id},                        # SELECT linked draft document
            None,                                        # DELETE chunks
            None,                                        # DELETE document
        ],
    )
    monkeypatch.setattr(db_client, "get_conn", factory)

    row = db_client.reject_overlay(overlay_id, approved_by=None)

    assert row["status"] == "rejected"
    assert len(captured["calls"]) == 4
    assert "DELETE FROM chunks" in captured["calls"][2]["sql"]
    assert captured["calls"][2]["params"]["document_id"] == document_id
    assert "DELETE FROM documents" in captured["calls"][3]["sql"]
    assert captured["calls"][3]["params"]["document_id"] == document_id


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


def test_list_overlays_containing_point_filters_approved_and_contains(monkeypatch) -> None:
    """Type 3 coverage-surfacing addition: metadata-only, no chunk search."""
    factory, captured = _fake_conn(
        fetchall_result=[{"id": uuid4(), "name": "Swiss Avenue Historic District", "status": "approved"}]
    )
    monkeypatch.setattr(db_client, "get_conn", factory)

    rows = db_client.list_overlays_containing_point(32.8, -96.78)

    assert len(rows) == 1
    assert rows[0]["status"] == "approved"
    assert captured["params"]["lat"] == 32.8
    assert captured["params"]["lng"] == -96.78
    assert "status = 'approved'" in captured["sql"]
    assert "ST_Contains" in captured["sql"]
