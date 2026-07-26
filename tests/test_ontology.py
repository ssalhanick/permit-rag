"""
tests/test_ontology.py — Field Ontology core (items 1-3)
========================================================
Vocabulary lookup, source binding, and per-type value validation. Pure data —
no DB, no model.
"""

from __future__ import annotations

from datetime import date

from forms.ontology import (
    ONTOLOGY,
    FieldType,
    SourceBinding,
    all_keys,
    fields_by_source,
    get_field,
    validate_value,
)


def test_vocabulary_is_keyed_and_typed() -> None:
    """Every field is reachable by key and carries a type + source."""
    assert get_field("work.valuation").type is FieldType.CURRENCY
    assert get_field("site.municipality").required is True
    assert get_field("nope.missing") is None
    assert "work.type" in all_keys()


def test_fields_by_source_lists_must_ask() -> None:
    """MUST_ASK facts (no upstream source) are enumerable to prompt the user."""
    must_ask = {f.key for f in fields_by_source(SourceBinding.MUST_ASK)}
    assert "contractor.license_number" in must_ask
    assert "electrical.service_amps" in must_ask


def test_currency_validation_normalizes() -> None:
    """Currency strips $ and commas, rejects negatives, tags USD."""
    ok = validate_value("work.valuation", "$12,500")
    assert ok.ok and ok.normalized == 12500.0 and ok.unit == "USD"
    assert validate_value("work.valuation", "-5").ok is False
    assert validate_value("work.valuation", "abc").ok is False


def test_enum_validation_is_closed() -> None:
    """Enum fields accept only their declared values."""
    assert validate_value("work.type", "Electrical").ok is True
    bad = validate_value("work.type", "Landscaping")
    assert bad.ok is False and "not in" in bad.error


def test_measurement_unit_must_match() -> None:
    """A measurement's unit must match the field's canonical unit."""
    ok = validate_value("structure.floor_area", "250 sqft")
    assert ok.ok and ok.normalized == 250.0 and ok.unit == "sqft"
    # bare number adopts the canonical unit
    assert validate_value("structure.floor_area", "250").ok is True
    # wrong unit is rejected
    assert validate_value("structure.floor_area", "250 acres").ok is False


def test_license_and_date_and_boolean() -> None:
    """License format, ISO date, and boolean coercion all validate."""
    assert validate_value("contractor.license_number", "TECL12345").ok is True
    assert validate_value("contractor.license_number", "!!").ok is False
    assert validate_value("work.start_date", "2026-08-01").normalized == "2026-08-01"
    assert validate_value("work.start_date", date(2026, 8, 1)).ok is True
    assert validate_value("work.owner_is_contractor", "yes").normalized is True
    assert validate_value("work.owner_is_contractor", "maybe").ok is False


def test_unknown_field_is_a_clean_failure() -> None:
    """Validating an unknown key returns ok=False, never raises."""
    res = validate_value("not.a.field", "x")
    assert res.ok is False and "unknown field" in res.error


def test_ontology_is_internally_consistent() -> None:
    """Every enum field declares values; every measurement declares a unit."""
    for fld in ONTOLOGY.values():
        if fld.type is FieldType.ENUM:
            assert fld.enum_values, f"{fld.key} is ENUM with no values"
        if fld.type is FieldType.MEASUREMENT:
            assert fld.unit, f"{fld.key} is MEASUREMENT with no unit"
