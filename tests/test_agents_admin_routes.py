"""
tests/test_agents_admin_routes.py — superadmin agent dashboard routes
=====================================================================
Fully mocked. Proves the acceptance criterion: non-superadmins get 403 on every
/admin/agents route; a superadmin can list the queue, resolve items, and apply a
metadata correction — with the write routed through ingestion.governance (never
inline) and a correction row recorded to close the loop.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth import get_optional_current_user
from api.main import app

SUPERADMIN = {"user_id": uuid4(), "role": "superadmin"}
ADMIN = {"user_id": uuid4(), "role": "admin"}


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _as(user):
    app.dependency_overrides[get_optional_current_user] = lambda: user


def _item(**over) -> dict:
    row = {
        "id": uuid4(),
        "source_agent": "metadata_validator",
        "kind": "metadata_needs_review",
        "severity": "medium",
        "blocking": False,
        "run_id": None,
        "entity_type": "document",
        "entity_id": "dallas-building-code",
        "title": "Metadata review: dallas-building-code",
        "evidence": {"proposals": []},
        "proposed_action": "Apply: effective_date→2019-06-15",
        "status": "open",
    }
    row.update(over)
    return row


# ── auth gate ────────────────────────────────────────────────


def test_action_items_403_for_admin(client) -> None:
    _as(ADMIN)
    assert client.get("/api/admin/agents/action-items").status_code == 403


def test_action_items_403_for_anonymous(client) -> None:
    _as(None)
    assert client.get("/api/admin/agents/action-items").status_code == 403


def test_metadata_review_403_for_admin(client) -> None:
    _as(ADMIN)
    assert client.get("/api/admin/agents/metadata-review").status_code == 403


def test_apply_403_for_admin(client) -> None:
    _as(ADMIN)
    r = client.post(
        "/api/admin/agents/metadata-review/dallas-building-code/apply",
        json={"item_id": str(uuid4()), "doc_type": "zoning_ordinance"},
    )
    assert r.status_code == 403


# ── action queue ─────────────────────────────────────────────


def test_list_action_items_superadmin(client, monkeypatch) -> None:
    _as(SUPERADMIN)
    from api.routes import agents_admin as route

    monkeypatch.setattr(route.db_client, "list_action_items", lambda **k: [_item()])
    r = client.get("/api/admin/agents/action-items")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_resolve_writes_correction(client, monkeypatch) -> None:
    _as(SUPERADMIN)
    from api.routes import agents_admin as route

    item = _item(status="resolved")
    monkeypatch.setattr(route.db_client, "resolve_action_item", lambda *a, **k: item)
    recorded: dict = {}
    monkeypatch.setattr(route.db_client, "insert_agent_correction",
                        lambda **k: recorded.update(k) or {"id": uuid4()})
    r = client.post(
        f"/api/admin/agents/action-items/{item['id']}/resolve",
        json={"status": "resolved", "note": "looks right"},
    )
    assert r.status_code == 200
    assert recorded["confirmed"] is True  # resolved → confirmed correction row
    assert recorded["attributed_agent"] == "metadata_validator"


def test_resolve_404_when_missing(client, monkeypatch) -> None:
    _as(SUPERADMIN)
    from api.routes import agents_admin as route

    monkeypatch.setattr(route.db_client, "resolve_action_item", lambda *a, **k: None)
    r = client.post(
        f"/api/admin/agents/action-items/{uuid4()}/resolve",
        json={"status": "dismissed"},
    )
    assert r.status_code == 404


# ── metadata review ──────────────────────────────────────────


def test_metadata_review_filters_agent(client, monkeypatch) -> None:
    _as(SUPERADMIN)
    from api.routes import agents_admin as route

    captured: dict = {}

    def _list(**kwargs):
        captured.update(kwargs)
        return [_item()]

    monkeypatch.setattr(route.db_client, "list_action_items", _list)
    r = client.get("/api/admin/agents/metadata-review")
    assert r.status_code == 200
    assert captured["source_agent"] == "metadata_validator"


def test_apply_routes_through_governance(client, monkeypatch) -> None:
    _as(SUPERADMIN)
    from api.routes import agents_admin as route

    gov_call: dict = {}

    def _apply(doc_id, **kwargs):
        gov_call.update({"doc_id": doc_id, **kwargs})
        return {"doc_id": doc_id, "effective_date": "2019-06-15"}

    monkeypatch.setattr(route.governance, "apply_metadata_correction", _apply)
    monkeypatch.setattr(route.db_client, "resolve_action_item", lambda *a, **k: _item(status="resolved"))
    monkeypatch.setattr(route.db_client, "insert_agent_correction", lambda **k: {"id": uuid4()})

    r = client.post(
        "/api/admin/agents/metadata-review/dallas-building-code/apply",
        json={
            "item_id": str(uuid4()),
            "effective_date": "2019-06-15",
            "doc_type": "zoning_ordinance",
        },
    )
    assert r.status_code == 200
    assert gov_call["doc_id"] == "dallas-building-code"
    assert gov_call["effective_date"] == date(2019, 6, 15)  # parsed to a date
    assert gov_call["doc_type"] == "zoning_ordinance"


def test_apply_400_when_no_fields(client, monkeypatch) -> None:
    _as(SUPERADMIN)
    r = client.post(
        "/api/admin/agents/metadata-review/dallas-building-code/apply",
        json={"item_id": str(uuid4())},
    )
    assert r.status_code == 400
