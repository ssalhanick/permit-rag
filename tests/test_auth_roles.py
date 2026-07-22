"""
tests/test_auth_roles.py — Unit tests for Cognito groups -> app role mapping.
"""

from __future__ import annotations

from api.auth import is_staff, is_superadmin, map_cognito_groups_to_role


def test_no_groups_defaults_to_member() -> None:
    assert map_cognito_groups_to_role(None) == "member"
    assert map_cognito_groups_to_role([]) == "member"


def test_unrelated_groups_default_to_member() -> None:
    assert map_cognito_groups_to_role(["beta-testers"]) == "member"


def test_admin_group_maps_to_admin() -> None:
    assert map_cognito_groups_to_role(["admin"]) == "admin"
    assert map_cognito_groups_to_role(["Admin"]) == "admin"


def test_superadmin_group_maps_to_superadmin() -> None:
    assert map_cognito_groups_to_role(["superadmin"]) == "superadmin"


def test_superadmin_takes_precedence_over_admin() -> None:
    assert map_cognito_groups_to_role(["admin", "superadmin"]) == "superadmin"


def test_is_staff() -> None:
    assert is_staff({"role": "admin"}) is True
    assert is_staff({"role": "superadmin"}) is True
    assert is_staff({"role": "member"}) is False
    assert is_staff(None) is False


def test_is_superadmin() -> None:
    assert is_superadmin({"role": "superadmin"}) is True
    assert is_superadmin({"role": "admin"}) is False
    assert is_superadmin(None) is False
