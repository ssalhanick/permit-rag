"""
tests/test_bids_service.py — db.client bid create/list/withdraw/award helpers,
plus bids/service.py's totals computation and BidDocument assembly.

Same fake-connection pattern as test_contractor_profiles.py: no real Postgres
connection. The award-declines-all-others transaction is the one invariant
tested hardest, since it's the single "several statements, one commit"
operation this feature adds.
"""

from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

import bids.service as bids_service
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


# ── bids/service.py: pure logic, no DB ──────────────────────────────


def test_compute_totals_sums_line_items_and_labor_material_split() -> None:
    line_items = [
        {"quantity": 2000, "unit_price": 5.5, "labor_amount": 6000, "material_amount": 5000},
        {"quantity": 1, "unit_price": 200, "labor_amount": 200, "material_amount": 0},
    ]
    total, labor, material = bids_service.compute_totals(line_items)
    assert total == 2000 * 5.5 + 1 * 200
    assert labor == 6200
    assert material == 5000


def test_compute_totals_defaults_missing_labor_material_to_zero() -> None:
    total, labor, material = bids_service.compute_totals([{"quantity": 10, "unit_price": 2}])
    assert total == 20
    assert labor == 0
    assert material == 0


def test_build_bid_document_assembles_from_three_lookups(monkeypatch) -> None:
    bid_row = {
        "id": uuid4(), "project_id": uuid4(), "contractor_profile_id": uuid4(), "license_id": uuid4(),
        "total_price": 100, "allowances": [], "exclusions": [], "payment_schedule": [],
        "permit_responsibility": None, "timeline_start": None, "timeline_end": None,
        "warranty_text": None, "warranty_years": None, "change_order_terms": None,
        "lien_waiver_included": False, "notes": None,
    }
    line_items = [{"description": "Reroof", "quantity": 100, "unit": "sq_ft", "unit_price": 5.0}]
    license_row = {
        "trade": "Roofing", "license_number": "TX1",
        "expiration_date": None, "insurance_provider": None, "insurance_expiration_date": None,
    }
    profile = {"business_name": "Acme Roofing"}

    monkeypatch.setattr(db_client, "list_bid_line_items", lambda bid_id: line_items)
    monkeypatch.setattr(db_client, "get_contractor_license", lambda license_id: license_row)
    monkeypatch.setattr(db_client, "get_contractor_profile", lambda profile_id: profile)

    document = bids_service.build_bid_document(bid_row)

    assert document.contractor_name == "Acme Roofing"
    assert document.trade == "Roofing"
    assert len(document.line_items) == 1
    assert document.line_items[0].description == "Reroof"


# ── db.client.create_bid ─────────────────────────────────────────


def test_create_bid_inserts_header_then_one_row_per_line_item(monkeypatch) -> None:
    bid_id = uuid4()
    conn = _FakeConn(one={"id": bid_id, "total_price": 100})
    _patch_conn(monkeypatch, conn)

    line_items = [
        {"description": "Reroof", "quantity": 100, "unit": "sq_ft", "unit_price": 5.0, "labor_amount": 300, "material_amount": 200},
        {"description": "Gutters", "quantity": 1, "unit": "each", "unit_price": 50, "labor_amount": 20, "material_amount": 30},
    ]
    row = db_client.create_bid(
        project_id=uuid4(), contractor_profile_id=uuid4(), license_id=uuid4(),
        total_price=100, line_items=line_items,
    )

    assert row["id"] == bid_id
    assert conn.committed is True
    assert len(conn.calls) == 3  # 1 header insert + 2 line-item inserts
    assert "INSERT INTO bids" in conn.calls[0][0]
    assert "INSERT INTO bid_line_items" in conn.calls[1][0]
    assert conn.calls[1][1]["line_index"] == 0
    assert conn.calls[2][1]["line_index"] == 1
    assert conn.calls[2][1]["description"] == "Gutters"


def test_create_bid_line_item_defaults(monkeypatch) -> None:
    conn = _FakeConn(one={"id": uuid4()})
    _patch_conn(monkeypatch, conn)

    db_client.create_bid(
        project_id=uuid4(), contractor_profile_id=uuid4(), license_id=uuid4(),
        total_price=50, line_items=[{"description": "Paint", "quantity": 1, "unit": "each", "unit_price": 50}],
    )
    _, params = conn.calls[1]
    assert params["labor_amount"] == 0
    assert params["material_amount"] == 0
    assert params["labor_hours"] is None


# ── db.client.withdraw_bid ────────────────────────────────────────


def test_withdraw_bid_returns_row_when_submitted(monkeypatch) -> None:
    bid_id = uuid4()
    conn = _FakeConn(one={"id": bid_id, "status": "withdrawn"})
    _patch_conn(monkeypatch, conn)

    row = db_client.withdraw_bid(bid_id)
    assert row["status"] == "withdrawn"
    assert conn.committed is True


def test_withdraw_bid_no_op_when_not_submitted(monkeypatch) -> None:
    conn = _FakeConn(one=None)  # the WHERE status='submitted' clause matched nothing
    _patch_conn(monkeypatch, conn)

    assert db_client.withdraw_bid(uuid4()) is None


# ── db.client.award_bid — the critical multi-statement transaction ──


def test_award_bid_awards_declines_others_and_updates_project_in_one_commit(monkeypatch) -> None:
    bid_id = uuid4()
    project_id = uuid4()
    conn = _FakeConn(one={"id": bid_id, "status": "awarded"})
    _patch_conn(monkeypatch, conn)

    row = db_client.award_bid(project_id, bid_id)

    assert row["status"] == "awarded"
    assert conn.committed is True
    assert len(conn.calls) == 3
    assert "UPDATE bids SET status = 'awarded'" in conn.calls[0][0]
    assert conn.calls[0][1] == (bid_id, project_id)
    assert "UPDATE bids SET status = 'declined'" in conn.calls[1][0]
    assert conn.calls[1][1] == (project_id, bid_id)
    assert "UPDATE projects SET marketplace_status = 'awarded'" in conn.calls[2][0]
    assert conn.calls[2][1] == (bid_id, project_id)


def test_award_bid_returns_none_and_does_not_touch_others_when_bid_not_found(monkeypatch) -> None:
    """A bid_id/project_id mismatch (e.g. bid belongs to a different project)
    must short-circuit before declining anyone else or touching the project."""
    conn = _FakeConn(one=None)
    _patch_conn(monkeypatch, conn)

    result = db_client.award_bid(uuid4(), uuid4())

    assert result is None
    assert len(conn.calls) == 1  # only the failed award attempt — no decline, no project update
    assert conn.committed is False


# ── db.client.close_bidding_without_award ────────────────────────


def test_close_bidding_declines_all_submitted_and_closes_project(monkeypatch) -> None:
    project_id = uuid4()
    conn = _FakeConn(one={"id": project_id, "marketplace_status": "closed"})
    _patch_conn(monkeypatch, conn)

    row = db_client.close_bidding_without_award(project_id)

    assert row["marketplace_status"] == "closed"
    assert conn.committed is True
    assert len(conn.calls) == 2
    assert "UPDATE bids SET status = 'declined'" in conn.calls[0][0]
    assert "UPDATE projects SET marketplace_status = 'closed'" in conn.calls[1][0]


# ── bids/service.py: list pass-through ───────────────────────────


def test_list_bids_for_project_delegates_to_db_client(monkeypatch) -> None:
    project_id = uuid4()
    rows = [{"id": uuid4()}, {"id": uuid4()}]
    conn = _FakeConn(many=rows)
    _patch_conn(monkeypatch, conn)

    assert bids_service.list_bids_for_project(project_id) == rows
