"""
tests/test_dashboard_v2_routes.py — dashboard v2 admin routes (Phase 5)
======================================================================
Scorecard, autonomy get/set, run trace, feedback summary, and the corrections
confirm-queue. Fully mocked. Every route is superadmin-gated (403 otherwise).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.auth import get_optional_current_user
from api.main import app
from api.routes import agents_admin as route

SUPERADMIN = {"user_id": uuid4(), "role": "superadmin"}
ADMIN = {"user_id": uuid4(), "role": "admin"}


@pytest.fixture
def client():
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def _as(user):
    app.dependency_overrides[get_optional_current_user] = lambda: user


def test_dashboard_routes_403_for_admin(client) -> None:
    """Every dashboard v2 GET is superadmin-only."""
    _as(ADMIN)
    for path in ("/scorecard", "/autonomy", "/feedback-summary", "/corrections"):
        assert client.get(f"/api/admin/agents{path}").status_code == 403


def test_scorecard_returns_rollup(client, monkeypatch) -> None:
    """The scorecard passes through the per-agent rollup."""
    _as(SUPERADMIN)
    monkeypatch.setattr(
        route.db_client, "agent_scorecard",
        lambda *, since: [{"agent_name": "answer_generator", "calls": 10}],
    )
    r = client.get("/api/admin/agents/scorecard?days=14")
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 14
    assert body["agents"][0]["agent_name"] == "answer_generator"


def test_set_autonomy_ok_and_ceiling_conflict(client, monkeypatch) -> None:
    """Setting a level within the ceiling succeeds; above it is a 409."""
    _as(SUPERADMIN)
    monkeypatch.setattr(
        route.db_client, "set_agent_autonomy",
        lambda a, s, *, current_level, updated_by=None: (
            {"agent_name": a, "current_level": current_level} if current_level != "L3" else None
        ),
    )
    ok = client.post("/api/admin/agents/autonomy/metadata_validator", json={"level": "L1"})
    assert ok.status_code == 200 and ok.json()["agent"]["current_level"] == "L1"

    over = client.post("/api/admin/agents/autonomy/metadata_validator", json={"level": "L3"})
    assert over.status_code == 409


def test_set_autonomy_rejects_bad_level(client) -> None:
    """A level outside L0-L3 is a validation error."""
    _as(SUPERADMIN)
    r = client.post("/api/admin/agents/autonomy/x", json={"level": "L9"})
    assert r.status_code == 422


def test_run_trace_404_when_missing(client, monkeypatch) -> None:
    """An unknown run id yields 404; a known one returns run + steps."""
    _as(SUPERADMIN)
    monkeypatch.setattr(route.db_client, "get_agent_run", lambda rid: None)
    assert client.get(f"/api/admin/agents/runs/{uuid4()}/trace").status_code == 404

    run_id = uuid4()
    monkeypatch.setattr(route.db_client, "get_agent_run", lambda rid: {"id": str(rid)})
    monkeypatch.setattr(route.db_client, "list_agent_steps", lambda rid: [{"agent_name": "manager"}])
    ok = client.get(f"/api/admin/agents/runs/{run_id}/trace")
    assert ok.status_code == 200 and ok.json()["steps"][0]["agent_name"] == "manager"


def test_feedback_summary_shapes(client, monkeypatch) -> None:
    """Feedback summary returns the vote counts + per-agent correction rate."""
    _as(SUPERADMIN)
    monkeypatch.setattr(route.db_client, "answer_feedback_counts", lambda *, since: {"up": 8, "down": 2})
    monkeypatch.setattr(route.db_client, "correction_rate_by_agent", lambda *, since: [])
    body = client.get("/api/admin/agents/feedback-summary").json()
    assert body["feedback"] == {"up": 8, "down": 2}


def test_corrections_queue_and_confirm(client, monkeypatch) -> None:
    """The unconfirmed queue lists rows; confirm flips one (with re-attribution)."""
    _as(SUPERADMIN)
    cid = uuid4()
    monkeypatch.setattr(
        route.db_client, "list_agent_corrections",
        lambda **k: [{"id": str(cid), "confirmed": False, "attributed_agent": None}],
    )
    listing = client.get("/api/admin/agents/corrections?confirmed=false")
    assert listing.status_code == 200 and listing.json()["count"] == 1

    captured = {}
    monkeypatch.setattr(
        route.db_client, "confirm_agent_correction",
        lambda cid_, **k: captured.update(k) or {"id": str(cid_), "confirmed": True, **k},
    )
    r = client.post(f"/api/admin/agents/corrections/{cid}/confirm",
                    json={"attributed_agent": "retriever"})
    assert r.status_code == 200
    assert r.json()["correction"]["confirmed"] is True
    assert captured["attributed_agent"] == "retriever"


def test_confirm_404_when_missing(client, monkeypatch) -> None:
    """Confirming a nonexistent correction is a 404."""
    _as(SUPERADMIN)
    monkeypatch.setattr(route.db_client, "confirm_agent_correction", lambda cid_, **k: None)
    r = client.post(f"/api/admin/agents/corrections/{uuid4()}/confirm", json={})
    assert r.status_code == 404
