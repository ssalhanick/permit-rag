"""
tests/test_project_jurisdiction_routes.py — address-driven jurisdiction
auto-resolution on project create/update.

Regression guard for the Phase 0 bug fix: `create_project`'s address-only
auto-resolve fallback used to read a nonexistent `.municipality` attribute off
`JurisdictionResolution` (only `.jurisdiction_id` exists), raising an
AttributeError that a bare `except Exception` swallowed — so the fallback was a
silent no-op. `test_create_project_auto_resolves_municipality_from_address_only`
fails against the pre-fix code and passes after it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app
from api.routes import projects as projects_route
from rag.jurisdiction_resolver import GeocodedAddress, JurisdictionResolution

client = TestClient(app)


def _current_user(user_id):
    return {"user_id": user_id, "role": "member", "username": "qa-user"}


def _project_row(project_id, owner_id, **overrides):
    now = datetime.now(UTC)
    row = {
        "id": project_id,
        "name": "Kitchen Remodel",
        "owner_user_id": owner_id,
        "is_archived": False,
        "created_at": now,
        "updated_at": now,
        "municipality": None,
        "address": None,
        "latitude": None,
        "longitude": None,
        "historic_district": None,
        "conservation_district": None,
    }
    row.update(overrides)
    return row


def _resolution(address: str, *, jurisdiction_id: str | None, lat=32.78, lng=-96.80) -> JurisdictionResolution:
    geocode = GeocodedAddress(
        input_address=address, matched_address=address, lat=lat, lng=lng, latency_ms=42,
    )
    return JurisdictionResolution(input_address=address, jurisdiction_id=jurisdiction_id, geocode=geocode)


def test_create_project_auto_resolves_municipality_from_address_only() -> None:
    """Address-only creation should populate municipality/lat/lng via the resolver."""
    owner_id = uuid4()
    project_id = uuid4()
    address = "123 Main St, Dallas, TX"

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch(
            "rag.jurisdiction_resolver.resolve_jurisdiction",
            return_value=_resolution(address, jurisdiction_id="dallas"),
        ), patch.object(
            projects_route.db_client, "create_project",
            return_value=_project_row(project_id, owner_id, municipality="dallas", address=address,
                                       latitude=32.78, longitude=-96.80),
        ) as mock_create:
            resp = client.post("/api/projects/", json={"name": "Kitchen Remodel", "address": address})

        assert resp.status_code == 201
        _, kwargs = mock_create.call_args
        assert kwargs["municipality"] == "dallas"
        assert kwargs["latitude"] == 32.78
        assert kwargs["longitude"] == -96.80
    finally:
        app.dependency_overrides.clear()


def test_create_project_address_resolution_failure_does_not_break_creation() -> None:
    """A resolver exception must fail open — the project is still created."""
    owner_id = uuid4()
    project_id = uuid4()
    address = "unresolvable address"

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch(
            "rag.jurisdiction_resolver.resolve_jurisdiction",
            side_effect=RuntimeError("boom"),
        ), patch.object(
            projects_route.db_client, "create_project",
            return_value=_project_row(project_id, owner_id, address=address),
        ) as mock_create:
            resp = client.post("/api/projects/", json={"name": "Kitchen Remodel", "address": address})

        assert resp.status_code == 201
        _, kwargs = mock_create.call_args
        assert kwargs["municipality"] is None
        assert kwargs["latitude"] is None
        assert kwargs["longitude"] is None
    finally:
        app.dependency_overrides.clear()


def test_update_project_address_change_reresolves_municipality() -> None:
    """PATCHing only `address` should re-derive municipality/lat/lng, not leave them frozen."""
    owner_id = uuid4()
    project_id = uuid4()
    new_address = "456 Oak St, Plano, TX"

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch(
                 "rag.jurisdiction_resolver.resolve_jurisdiction",
                 return_value=_resolution(new_address, jurisdiction_id="plano", lat=33.02, lng=-96.70),
             ), \
             patch("rag.gis.lookup_jurisdiction_overlays", return_value=(None, None)), \
             patch.object(
                 projects_route.db_client, "update_project",
                 return_value=_project_row(project_id, owner_id, municipality="plano", address=new_address,
                                            latitude=33.02, longitude=-96.70),
             ) as mock_update:
            resp = client.patch(f"/api/projects/{project_id}", json={"address": new_address})

        assert resp.status_code == 200
        _, kwargs = mock_update.call_args
        assert kwargs["municipality"] == "plano"
        assert kwargs["latitude"] == 33.02
        assert kwargs["longitude"] == -96.70
    finally:
        app.dependency_overrides.clear()


def test_update_project_explicit_municipality_overrides_auto_resolve() -> None:
    """An explicit `municipality` in the same PATCH must suppress auto-resolve entirely."""
    owner_id = uuid4()
    project_id = uuid4()
    address = "456 Oak St, Plano, TX"

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch("rag.jurisdiction_resolver.resolve_jurisdiction") as mock_resolve, \
             patch.object(
                 projects_route.db_client, "update_project",
                 return_value=_project_row(project_id, owner_id, municipality="mckinney", address=address),
             ) as mock_update:
            resp = client.patch(
                f"/api/projects/{project_id}",
                json={"address": address, "municipality": "mckinney"},
            )

        assert resp.status_code == 200
        mock_resolve.assert_not_called()
        _, kwargs = mock_update.call_args
        assert kwargs["municipality"] == "mckinney"
    finally:
        app.dependency_overrides.clear()


def test_update_project_address_unchanged_does_not_reresolve() -> None:
    """A PATCH that never touches `address` should never call the resolver."""
    owner_id = uuid4()
    project_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch("rag.jurisdiction_resolver.resolve_jurisdiction") as mock_resolve, \
             patch.object(
                 projects_route.db_client, "update_project",
                 return_value=_project_row(project_id, owner_id, budget="$10k-$25k"),
             ) as mock_update:
            resp = client.patch(f"/api/projects/{project_id}", json={"budget": "$10k-$25k"})

        assert resp.status_code == 200
        mock_resolve.assert_not_called()
        mock_update.assert_called_once()
    finally:
        app.dependency_overrides.clear()


def test_project_coverage_route_returns_check_coverage_result() -> None:
    """GET .../coverage should be a thin, deterministic wrapper over rag.coverage."""
    from rag.coverage import CoverageResult

    owner_id = uuid4()
    project_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 projects_route.db_client, "get_project",
                 return_value=_project_row(project_id, owner_id, municipality="frisco"),
             ), \
             patch(
                 "rag.coverage.check_coverage",
                 return_value=CoverageResult("no_documents", "frisco", "We don't yet have frisco..."),
             ) as mock_check_coverage:
            resp = client.get(f"/api/projects/{project_id}/coverage")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_documents"
        assert body["municipality"] == "frisco"
        assert body["is_covered"] is False
        mock_check_coverage.assert_called_once_with(
            municipality="frisco", latitude=None, longitude=None,
        )
    finally:
        app.dependency_overrides.clear()


def test_project_coverage_route_surfaces_approved_overlays() -> None:
    """Type 3 addition: the coverage response includes any approved overlay
    whose boundary contains the project's address, alongside municipality status."""
    from datetime import UTC, datetime

    from rag.coverage import CoverageResult

    owner_id = uuid4()
    project_id = uuid4()
    overlay_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 projects_route.db_client, "get_project",
                 return_value=_project_row(
                     project_id, owner_id, municipality="dallas",
                     latitude=32.8, longitude=-96.78,
                 ),
             ), \
             patch(
                 "rag.coverage.check_coverage",
                 return_value=CoverageResult("covered", "dallas", "This area is in our coverage area."),
             ), \
             patch.object(
                 projects_route.db_client, "list_overlays_containing_point",
                 return_value=[{
                     "id": overlay_id, "name": "Swiss Avenue Historic District",
                     "overlay_type": "historic_district", "jurisdiction_id": "dallas",
                     "status": "approved", "petitioning_project_id": None,
                     "approved_by": None, "approved_at": datetime.now(UTC),
                     "notes": None, "created_at": datetime.now(UTC),
                 }],
             ) as mock_overlays:
            resp = client.get(f"/api/projects/{project_id}/coverage")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["overlays"]) == 1
        assert body["overlays"][0]["name"] == "Swiss Avenue Historic District"
        mock_overlays.assert_called_once_with(32.8, -96.78)
    finally:
        app.dependency_overrides.clear()


def test_project_coverage_route_overlays_empty_without_coordinates() -> None:
    """No lat/lng on file -> empty overlays list, no DB round trip attempted."""
    from rag.coverage import CoverageResult

    owner_id = uuid4()
    project_id = uuid4()

    app.dependency_overrides[projects_route.get_current_user] = lambda: _current_user(owner_id)
    try:
        with patch.object(projects_route.db_client, "get_project_role", return_value="owner"), \
             patch.object(
                 projects_route.db_client, "get_project",
                 return_value=_project_row(project_id, owner_id, municipality="frisco"),
             ), \
             patch(
                 "rag.coverage.check_coverage",
                 return_value=CoverageResult("no_documents", "frisco", "..."),
             ), \
             patch.object(
                 projects_route.db_client, "list_overlays_containing_point",
             ) as mock_overlays:
            resp = client.get(f"/api/projects/{project_id}/coverage")

        assert resp.status_code == 200
        assert resp.json()["overlays"] == []
        mock_overlays.assert_not_called()
    finally:
        app.dependency_overrides.clear()
