"""
tests/test_coverage.py — rag/coverage.py deterministic coverage-area check.
"""

from __future__ import annotations

from unittest.mock import patch

from rag.coverage import CoverageResult, check_coverage, covered_municipalities


@patch("db.client.list_documents")
def test_covered_municipality_with_active_documents(mock_list_documents) -> None:
    mock_list_documents.return_value = [{"doc_id": "dallas-fence"}]

    result = check_coverage(municipality="dallas", latitude=None, longitude=None)

    assert result.status == "covered"
    assert result.is_covered is True
    mock_list_documents.assert_called_once_with(municipality="dallas", status="active")


@patch("db.client.list_documents")
def test_seeded_but_empty_municipality_is_no_documents(mock_list_documents) -> None:
    """Frisco/McKinney today: a real jurisdictions row, zero active documents."""
    mock_list_documents.return_value = []

    result = check_coverage(municipality="frisco", latitude=None, longitude=None)

    assert result.status == "no_documents"
    assert result.is_covered is False
    assert "frisco" in result.message


@patch("rag.jurisdiction_resolver._point_in_polygon")
@patch("db.client.list_documents")
def test_lat_lng_resolves_to_covered_municipality(mock_list_documents, mock_point_in_polygon) -> None:
    mock_point_in_polygon.return_value = "plano"
    mock_list_documents.return_value = [{"doc_id": "plano-permit"}]

    result = check_coverage(municipality=None, latitude=33.02, longitude=-96.70)

    assert result.status == "covered"
    assert result.municipality == "plano"
    mock_point_in_polygon.assert_called_once_with(33.02, -96.70)


@patch("rag.jurisdiction_resolver._point_in_polygon")
def test_lat_lng_outside_every_boundary_is_no_boundary_data(mock_point_in_polygon) -> None:
    mock_point_in_polygon.return_value = None

    result = check_coverage(municipality=None, latitude=40.0, longitude=-74.0)

    assert result.status == "no_boundary_data"
    assert result.is_covered is False


def test_nothing_given_is_unresolved() -> None:
    result = check_coverage(municipality=None, latitude=None, longitude=None)
    assert result.status == "unresolved"
    assert result.is_covered is False


def test_coverage_result_is_covered_property() -> None:
    assert CoverageResult("covered", "dallas", "msg").is_covered is True
    assert CoverageResult("no_documents", "frisco", "msg").is_covered is False


@patch("db.client.list_covered_municipalities")
def test_covered_municipalities_strips_city_of_prefix(mock_list_covered) -> None:
    mock_list_covered.return_value = [
        {"id": "dallas", "name": "City of Dallas"},
        {"id": "fortworth", "name": "City of Fort Worth"},
        {"id": "plano", "name": "City of Plano"},
    ]

    assert covered_municipalities() == ["Dallas", "Fort Worth", "Plano"]


@patch("db.client.list_covered_municipalities", side_effect=RuntimeError("db unreachable"))
def test_covered_municipalities_falls_back_when_db_unreachable(_mock) -> None:
    assert covered_municipalities() == ["Dallas", "Plano", "Fort Worth"]


@patch("db.client.list_covered_municipalities", return_value=[])
def test_covered_municipalities_falls_back_when_empty(_mock) -> None:
    assert covered_municipalities() == ["Dallas", "Plano", "Fort Worth"]
