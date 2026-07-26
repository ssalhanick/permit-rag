"""
tests/test_feedback_route.py — POST /query/feedback (Phase 5 feedback loop)
===========================================================================
Answer-level thumbs up/down. The route validates the run exists, then upserts
one vote per (run_id, user_id). Fully mocked — no DB, no model, no network.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from api.routes import query as query_route


def _override_user(user_id):
    """Install a fake authenticated user for the duration of a test."""
    app.dependency_overrides[query_route.get_current_user] = lambda: {
        "user_id": user_id,
        "role": "member",
        "username": "tester",
    }


def test_feedback_up_is_recorded(monkeypatch) -> None:
    """A thumbs-up on a known run returns 200 and upserts the vote."""
    from db import client as db_client

    run_id = uuid4()
    user_id = uuid4()
    captured = {}

    monkeypatch.setattr(db_client, "get_agent_run", lambda rid: {"id": rid})

    def _fake_upsert(**kwargs):
        captured.update(kwargs)
        return {"id": uuid4(), "run_id": kwargs["run_id"], "rating": kwargs["rating"]}

    monkeypatch.setattr(db_client, "upsert_answer_feedback", _fake_upsert)
    _override_user(user_id)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/query/feedback",
            json={"run_id": str(run_id), "rating": "up"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rating"] == "up"
        assert body["run_id"] == str(run_id)
        # The authenticated user is attributed; no comment sent.
        assert captured["run_id"] == run_id
        assert captured["user_id"] == user_id
        assert captured["rating"] == "up"
        assert captured["comment"] is None
    finally:
        app.dependency_overrides.clear()


def test_feedback_down_with_comment_is_stored(monkeypatch) -> None:
    """A thumbs-down carries its free-text comment through to the writer."""
    from db import client as db_client

    run_id = uuid4()
    captured = {}
    monkeypatch.setattr(db_client, "get_agent_run", lambda rid: {"id": rid})

    def _fake_upsert(**kwargs):
        captured.update(kwargs)
        return {"id": uuid4(), "run_id": kwargs["run_id"], "rating": kwargs["rating"]}

    monkeypatch.setattr(db_client, "upsert_answer_feedback", _fake_upsert)
    _override_user(uuid4())
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/query/feedback",
            json={"run_id": str(run_id), "rating": "down", "comment": "Wrong setback."},
        )
        assert resp.status_code == 200
        assert resp.json()["rating"] == "down"
        assert captured["comment"] == "Wrong setback."
    finally:
        app.dependency_overrides.clear()


def test_feedback_unknown_run_returns_404(monkeypatch) -> None:
    """Feedback on a run that does not exist is a 404, not a silent insert."""
    from db import client as db_client

    called = {"upsert": False}
    monkeypatch.setattr(db_client, "get_agent_run", lambda rid: None)

    def _fake_upsert(**kwargs):
        called["upsert"] = True
        return {}

    monkeypatch.setattr(db_client, "upsert_answer_feedback", _fake_upsert)
    _override_user(uuid4())
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/query/feedback",
            json={"run_id": str(uuid4()), "rating": "up"},
        )
        assert resp.status_code == 404
        assert called["upsert"] is False  # never wrote for a missing run
    finally:
        app.dependency_overrides.clear()


def test_feedback_invalid_rating_returns_422(monkeypatch) -> None:
    """Ratings outside {up, down} are rejected by schema validation."""
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_agent_run", lambda rid: {"id": rid})
    _override_user(uuid4())
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/query/feedback",
            json={"run_id": str(uuid4()), "rating": "meh"},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_feedback_missing_run_id_returns_422(monkeypatch) -> None:
    """run_id is required — omitting it is a validation error."""
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_agent_run", lambda rid: {"id": rid})
    _override_user(uuid4())
    try:
        client = TestClient(app)
        resp = client.post("/api/query/feedback", json={"rating": "up"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
