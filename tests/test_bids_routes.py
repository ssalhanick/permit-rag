"""
tests/test_bids_routes.py — bid submission/list/withdraw/award route behavior.

Same TestClient + app.dependency_overrides + patch.object(db_client, ...)
pattern as the other route test files. api.routes.bids._evaluate is stubbed
out in most tests since its internals are already covered by
tests/test_bid_evaluator.py — these tests are about routing and permissions,
not evaluation content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.contractor_auth import require_biddable_contractor, require_contractor_profile
from api.main import app
from api.routes import bids as bids_route

client = TestClient(app)

_STUB_EVALUATION = {
    "completeness_score": 1.0, "missing_clauses": [], "red_flags": [],
    "price_assessments": [], "llm_flags": [], "disclaimer": "Estimates only.",
}


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


def _profile_row(profile_id, user_id):
    return {"id": profile_id, "user_id": user_id, "business_name": "Acme Roofing"}


def _license_row(license_id, profile_id):
    return {"id": license_id, "contractor_profile_id": profile_id, "trade": "Roofing", "license_number": "TX12345"}


def _project_row(project_id, **overrides):
    row = {"id": project_id, "marketplace_status": "open", "address": None}
    row.update(overrides)
    return row


def _bid_row(bid_id, project_id, contractor_profile_id, license_id, **overrides):
    now = datetime.now(UTC)
    row = {
        "id": bid_id, "project_id": project_id, "contractor_profile_id": contractor_profile_id,
        "license_id": license_id, "status": "submitted", "total_price": 100,
        "labor_total": 60, "material_total": 40, "allowances": [], "exclusions": [],
        "payment_schedule": [], "permit_responsibility": None, "timeline_start": None,
        "timeline_end": None, "timeline_notes": None, "warranty_text": None, "warranty_years": None,
        "change_order_terms": None, "lien_waiver_included": False, "materials_source": "unspecified",
        "materials_source_connector": None, "materials_source_notes": None, "notes": None,
        "submitted_at": now, "decided_at": None, "created_at": now, "updated_at": now,
    }
    row.update(overrides)
    return row


_VALID_BID_PAYLOAD = {"line_items": [{"description": "Reroof", "quantity": 100, "unit": "sq_ft", "unit_price": 5.0}]}


# ── submit_bid ────────────────────────────────────────────────────


def test_submit_bid_success() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()
    project_id = uuid4()
    bid_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_biddable_contractor] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(bids_route.db_client, "get_project", return_value=_project_row(project_id)), \
             patch.object(bids_route.db_client, "get_contractor_license", return_value=_license_row(license_id, profile_id)), \
             patch.object(
                 bids_route.bids_service, "create_bid",
                 return_value=_bid_row(bid_id, project_id, profile_id, license_id),
             ) as mock_create, \
             patch.object(bids_route.db_client, "list_bid_line_items", return_value=[]), \
             patch.object(bids_route.db_client, "get_contractor_profile", return_value=_profile_row(profile_id, user_id)), \
             patch.object(bids_route, "_evaluate", return_value=_STUB_EVALUATION):
            payload = dict(_VALID_BID_PAYLOAD, license_id=str(license_id))
            resp = client.post(f"/api/projects/{project_id}/bids", json=payload)

        assert resp.status_code == 201
        assert resp.json()["status"] == "submitted"
        mock_create.assert_called_once()
        _, kwargs = mock_create.call_args
        assert kwargs["contractor_profile_id"] == profile_id
    finally:
        app.dependency_overrides.clear()


def test_submit_bid_rejects_when_project_not_open() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    project_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_biddable_contractor] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            bids_route.db_client, "get_project",
            return_value=_project_row(project_id, marketplace_status="unlisted"),
        ), patch.object(bids_route.bids_service, "create_bid") as mock_create:
            payload = dict(_VALID_BID_PAYLOAD, license_id=str(uuid4()))
            resp = client.post(f"/api/projects/{project_id}/bids", json=payload)

        assert resp.status_code == 422
        mock_create.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_submit_bid_404_when_license_not_owned_by_contractor() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    other_profile_id = uuid4()
    license_id = uuid4()
    project_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_biddable_contractor] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(bids_route.db_client, "get_project", return_value=_project_row(project_id)), \
             patch.object(bids_route.db_client, "get_contractor_license", return_value=_license_row(license_id, other_profile_id)), \
             patch.object(bids_route.bids_service, "create_bid") as mock_create:
            payload = dict(_VALID_BID_PAYLOAD, license_id=str(license_id))
            resp = client.post(f"/api/projects/{project_id}/bids", json=payload)

        assert resp.status_code == 404
        mock_create.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_submit_bid_conflict_on_duplicate_active_bid() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()
    project_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    app.dependency_overrides[require_biddable_contractor] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(bids_route.db_client, "get_project", return_value=_project_row(project_id)), \
             patch.object(bids_route.db_client, "get_contractor_license", return_value=_license_row(license_id, profile_id)), \
             patch.object(
                 bids_route.bids_service, "create_bid",
                 side_effect=Exception(
                     'duplicate key value violates unique constraint "uq_bids_one_active_per_contractor_project"'
                 ),
             ):
            payload = dict(_VALID_BID_PAYLOAD, license_id=str(license_id))
            resp = client.post(f"/api/projects/{project_id}/bids", json=payload)

        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()


# ── list_project_bids ─────────────────────────────────────────────


def test_list_project_bids_requires_project_role() -> None:
    user_id = uuid4()
    project_id = uuid4()
    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(bids_route.db_client, "get_project_role", return_value=None):
            resp = client.get(f"/api/projects/{project_id}/bids")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_list_project_bids_success_for_member() -> None:
    user_id = uuid4()
    project_id = uuid4()
    bid_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(bids_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 bids_route.db_client, "list_bids_for_project",
                 return_value=[_bid_row(bid_id, project_id, profile_id, license_id)],
             ), \
             patch.object(bids_route.db_client, "list_bid_line_items", return_value=[]), \
             patch.object(bids_route.db_client, "get_contractor_profile", return_value=_profile_row(profile_id, user_id)), \
             patch.object(bids_route, "_evaluate", return_value=_STUB_EVALUATION):
            resp = client.get(f"/api/projects/{project_id}/bids")

        assert resp.status_code == 200
        assert len(resp.json()) == 1
    finally:
        app.dependency_overrides.clear()


# ── list_my_bids ──────────────────────────────────────────────────


def test_list_my_bids_scoped_to_own_profile() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()
    project_id = uuid4()
    bid_id = uuid4()

    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            bids_route.db_client, "list_bids_for_contractor",
            return_value=[_bid_row(bid_id, project_id, profile_id, license_id)],
        ) as mock_list, \
             patch.object(bids_route.db_client, "list_bid_line_items", return_value=[]), \
             patch.object(bids_route.db_client, "get_contractor_profile", return_value=_profile_row(profile_id, user_id)):
            resp = client.get("/api/bids/mine")

        assert resp.status_code == 200
        mock_list.assert_called_once_with(profile_id)
    finally:
        app.dependency_overrides.clear()


# ── get_bid ───────────────────────────────────────────────────────


def test_get_bid_403_when_neither_owner_nor_member() -> None:
    user_id = uuid4()
    bid_id = uuid4()
    project_id = uuid4()
    other_profile_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            bids_route.db_client, "get_bid",
            return_value=_bid_row(bid_id, project_id, other_profile_id, license_id),
        ), patch.object(bids_route.db_client, "get_contractor_profile_by_user", return_value=None), \
             patch.object(bids_route.db_client, "get_project_role", return_value=None):
            resp = client.get(f"/api/bids/{bid_id}")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_get_bid_allowed_for_owning_contractor() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    bid_id = uuid4()
    project_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(
            bids_route.db_client, "get_bid",
            return_value=_bid_row(bid_id, project_id, profile_id, license_id),
        ), patch.object(bids_route.db_client, "get_contractor_profile_by_user", return_value=_profile_row(profile_id, user_id)), \
             patch.object(bids_route.db_client, "get_project_role", return_value=None), \
             patch.object(bids_route.db_client, "list_bid_line_items", return_value=[]), \
             patch.object(bids_route.db_client, "get_contractor_profile", return_value=_profile_row(profile_id, user_id)), \
             patch.object(bids_route, "_evaluate", return_value=_STUB_EVALUATION):
            resp = client.get(f"/api/bids/{bid_id}")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.clear()


# ── withdraw_bid ──────────────────────────────────────────────────


def test_withdraw_bid_404_when_not_own() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    other_profile_id = uuid4()
    bid_id = uuid4()
    project_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            bids_route.db_client, "get_bid",
            return_value=_bid_row(bid_id, project_id, other_profile_id, license_id),
        ), patch.object(bids_route.db_client, "withdraw_bid") as mock_withdraw:
            resp = client.post(f"/api/bids/{bid_id}/withdraw")
        assert resp.status_code == 404
        mock_withdraw.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_withdraw_bid_success() -> None:
    user_id = uuid4()
    profile_id = uuid4()
    bid_id = uuid4()
    project_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[require_contractor_profile] = lambda: _profile_row(profile_id, user_id)
    try:
        with patch.object(
            bids_route.db_client, "get_bid",
            return_value=_bid_row(bid_id, project_id, profile_id, license_id),
        ), patch.object(
            bids_route.db_client, "withdraw_bid",
            return_value=_bid_row(bid_id, project_id, profile_id, license_id, status="withdrawn"),
        ), patch.object(bids_route.db_client, "list_bid_line_items", return_value=[]), \
             patch.object(bids_route.db_client, "get_contractor_profile", return_value=_profile_row(profile_id, user_id)):
            resp = client.post(f"/api/bids/{bid_id}/withdraw")
        assert resp.status_code == 200
        assert resp.json()["status"] == "withdrawn"
    finally:
        app.dependency_overrides.clear()


# ── award_bid ─────────────────────────────────────────────────────


def test_award_bid_403_when_not_owner() -> None:
    user_id = uuid4()
    project_id = uuid4()
    bid_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(bids_route.db_client, "get_project_role", return_value="editor"), \
             patch.object(bids_route.db_client, "award_bid") as mock_award:
            resp = client.post(f"/api/projects/{project_id}/bids/{bid_id}/award")
        assert resp.status_code == 403
        mock_award.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_award_bid_422_when_not_submitted() -> None:
    user_id = uuid4()
    project_id = uuid4()
    bid_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(bids_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 bids_route.db_client, "get_bid",
                 return_value=_bid_row(bid_id, project_id, profile_id, license_id, status="withdrawn"),
             ), patch.object(bids_route.db_client, "award_bid") as mock_award:
            resp = client.post(f"/api/projects/{project_id}/bids/{bid_id}/award")
        assert resp.status_code == 422
        mock_award.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_award_bid_success() -> None:
    user_id = uuid4()
    project_id = uuid4()
    bid_id = uuid4()
    profile_id = uuid4()
    license_id = uuid4()

    app.dependency_overrides[bids_route.get_current_user] = lambda: _current_user(user_id)
    try:
        with patch.object(bids_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 bids_route.db_client, "get_bid",
                 return_value=_bid_row(bid_id, project_id, profile_id, license_id, status="submitted"),
             ), patch.object(
                 bids_route.db_client, "award_bid",
                 return_value=_bid_row(bid_id, project_id, profile_id, license_id, status="awarded"),
             ) as mock_award, \
             patch.object(bids_route.db_client, "list_bid_line_items", return_value=[]), \
             patch.object(bids_route.db_client, "get_contractor_profile", return_value=_profile_row(profile_id, user_id)):
            resp = client.post(f"/api/projects/{project_id}/bids/{bid_id}/award")

        assert resp.status_code == 200
        assert resp.json()["status"] == "awarded"
        mock_award.assert_called_once_with(project_id, bid_id)
    finally:
        app.dependency_overrides.clear()
