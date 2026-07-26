"""
forms/ontology.py — Field Ontology core (items 1-3)
===================================================
Phase 5 lands the *core* of the Field Ontology (docs/agent_architecture.md
"What the Field Ontology actually is", parts 1-3): the canonical vocabulary of
project facts, a type + validation per fact, and the source binding that says
where each fact comes from. The hard part — the per-form mapping corpus (part 4)
— accretes in Phases 6-7; the core lands now because it is cheap and has
non-form consumers already (Project Memory, Permit Strategy) that benefit from a
shared vocabulary immediately.

**A code module, not a migration.** Like the Phase-4 fragment library, the
canonical vocabulary is git-tracked content that changes with a code deploy, not
runtime data — so it lives here, versioned in git, rather than behind a DB
migration. The DB tables arrive with the per-form mappings (Phase 6), which *are*
data that changes without a deploy.

Import boundary: forms/ → db/, standard library only (AGENTS.md). Pure data +
deterministic validation — no model, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class FieldType(StrEnum):
    """The validation class of a canonical fact."""

    TEXT = "text"
    ENUM = "enum"
    INTEGER = "integer"
    CURRENCY = "currency"          # USD amount
    MEASUREMENT = "measurement"    # a number carrying a unit
    LICENSE_NUMBER = "license_number"
    DATE = "date"
    BOOLEAN = "boolean"


class SourceBinding(StrEnum):
    """Where a fact is sourced from — item 3 of the ontology core."""

    PROJECT = "project"        # projects table
    KICKOFF = "kickoff"        # the kickoff wizard/dialog
    ROOM_SCAN = "room_scan"    # on-device room-scan metrics
    GIS = "gis"                # geocode / parcel lookup
    PROFILE = "profile"        # user profile
    DERIVED = "derived"        # computed from other facts
    MUST_ASK = "must_ask"      # no source — the user must supply it


@dataclass(frozen=True)
class CanonicalField:
    """One named fact: its type, source, and (where bounded) its value space."""

    key: str
    label: str
    type: FieldType
    source: SourceBinding
    unit: str | None = None                 # MEASUREMENT: canonical unit
    enum_values: tuple[str, ...] = ()        # ENUM: the closed value set
    required: bool = False


def _f(*args, **kwargs) -> CanonicalField:
    """Terse constructor for the seed table below."""
    return CanonicalField(*args, **kwargs)


# The core vocabulary — a representative seed across the permit domains. Not the
# full 150-300 (that is the accreting design exercise); enough that the non-form
# consumers have real facts to bind to, spanning every FieldType + SourceBinding.
_FIELDS: tuple[CanonicalField, ...] = (
    # parcel / site (GIS)
    _f("parcel.legal_description", "Legal description", FieldType.TEXT, SourceBinding.GIS),
    _f("parcel.zoning_district", "Zoning district", FieldType.TEXT, SourceBinding.GIS),
    _f("parcel.lot_area", "Lot area", FieldType.MEASUREMENT, SourceBinding.GIS, unit="sqft"),
    _f("site.municipality", "Municipality", FieldType.TEXT, SourceBinding.PROJECT, required=True),
    # structure
    _f("structure.occupancy_group", "Occupancy group", FieldType.ENUM, SourceBinding.MUST_ASK,
       enum_values=("R-3", "R-2", "B", "M", "A-2", "U")),
    _f("structure.stories", "Number of stories", FieldType.INTEGER, SourceBinding.KICKOFF),
    _f("structure.floor_area", "Floor area", FieldType.MEASUREMENT, SourceBinding.ROOM_SCAN, unit="sqft"),
    _f("structure.ceiling_height", "Ceiling height", FieldType.MEASUREMENT, SourceBinding.ROOM_SCAN, unit="ft"),
    # trades
    _f("electrical.service_amps", "Electrical service", FieldType.MEASUREMENT, SourceBinding.MUST_ASK, unit="A"),
    _f("plumbing.fixture_count", "Plumbing fixtures", FieldType.INTEGER, SourceBinding.KICKOFF),
    # work / scope
    _f("work.type", "Work type", FieldType.ENUM, SourceBinding.KICKOFF,
       enum_values=("Plumbing", "Electrical", "HVAC / Mechanical", "Structural / Framing",
                    "Roofing", "Deck / Patio Build", "Pool / Spa", "Demolition",
                    "Windows / Doors", "Paint / Drywall", "Flooring", "Tile / Backsplash"),
       required=True),
    _f("work.valuation", "Project valuation", FieldType.CURRENCY, SourceBinding.KICKOFF, required=True),
    _f("work.start_date", "Planned start date", FieldType.DATE, SourceBinding.KICKOFF),
    _f("work.owner_is_contractor", "Owner is the contractor", FieldType.BOOLEAN, SourceBinding.PROFILE),
    # contractor
    _f("contractor.license_number", "Contractor license #", FieldType.LICENSE_NUMBER, SourceBinding.MUST_ASK),
    _f("contractor.name", "Contractor name", FieldType.TEXT, SourceBinding.PROFILE),
)

ONTOLOGY: dict[str, CanonicalField] = {fld.key: fld for fld in _FIELDS}

# License-number shapes (TX trades). Loose by design — a format gate, not a registry.
_LICENSE_RE = re.compile(r"^[A-Za-z]{0,4}\d{4,8}$")
_MEASUREMENT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([A-Za-z²]+)?\s*$")


def get_field(key: str) -> CanonicalField | None:
    """Look up a canonical field by key, or None if it is not in the ontology."""
    return ONTOLOGY.get(key)


def fields_by_source(source: SourceBinding) -> list[CanonicalField]:
    """Every field bound to a given source — e.g. all MUST_ASK facts to prompt for."""
    return [fld for fld in _FIELDS if fld.source == source]


def all_keys() -> list[str]:
    """Sorted canonical keys — the vocabulary the form mapper proposes against."""
    return sorted(ONTOLOGY)


@dataclass
class ValidationResult:
    """Outcome of validating a value against a canonical field."""

    ok: bool
    normalized: object = None
    error: str = ""
    unit: str | None = None


def validate_value(key: str, value: object) -> ValidationResult:
    """Validate + normalize a raw value against its canonical field's type.

    Deterministic and total — an unknown key or a bad value returns
    ``ok=False`` with a reason, never raises.
    """
    fld = ONTOLOGY.get(key)
    if fld is None:
        return ValidationResult(False, error=f"unknown field '{key}'")
    return _VALIDATORS[fld.type](fld, value)


def _v_text(fld: CanonicalField, value: object) -> ValidationResult:
    text = str(value).strip()
    return ValidationResult(bool(text), normalized=text, error="" if text else "empty")


def _v_enum(fld: CanonicalField, value: object) -> ValidationResult:
    text = str(value).strip()
    if text in fld.enum_values:
        return ValidationResult(True, normalized=text)
    return ValidationResult(False, error=f"'{text}' not in {list(fld.enum_values)}")


def _v_integer(fld: CanonicalField, value: object) -> ValidationResult:
    try:
        return ValidationResult(True, normalized=int(str(value).strip()))
    except (TypeError, ValueError):
        return ValidationResult(False, error=f"'{value}' is not an integer")


def _v_currency(fld: CanonicalField, value: object) -> ValidationResult:
    cleaned = re.sub(r"[,$\s]", "", str(value))
    try:
        amount = round(float(cleaned), 2)
    except ValueError:
        return ValidationResult(False, error=f"'{value}' is not a currency amount")
    if amount < 0:
        return ValidationResult(False, error="currency cannot be negative")
    return ValidationResult(True, normalized=amount, unit="USD")


def _v_measurement(fld: CanonicalField, value: object) -> ValidationResult:
    m = _MEASUREMENT_RE.match(str(value))
    if not m:
        return ValidationResult(False, error=f"'{value}' is not a measurement")
    number = float(m.group(1))
    unit = m.group(2) or fld.unit
    if fld.unit and unit and unit.lower() != fld.unit.lower():
        return ValidationResult(False, error=f"expected unit '{fld.unit}', got '{unit}'")
    return ValidationResult(True, normalized=number, unit=fld.unit)


def _v_license(fld: CanonicalField, value: object) -> ValidationResult:
    text = str(value).strip()
    if _LICENSE_RE.match(text):
        return ValidationResult(True, normalized=text.upper())
    return ValidationResult(False, error=f"'{text}' is not a license-number format")


def _v_date(fld: CanonicalField, value: object) -> ValidationResult:
    if isinstance(value, date):
        return ValidationResult(True, normalized=value.isoformat())
    try:
        return ValidationResult(True, normalized=date.fromisoformat(str(value).strip()).isoformat())
    except ValueError:
        return ValidationResult(False, error=f"'{value}' is not an ISO date")


def _v_boolean(fld: CanonicalField, value: object) -> ValidationResult:
    text = str(value).strip().lower()
    if text in ("true", "yes", "1", "y"):
        return ValidationResult(True, normalized=True)
    if text in ("false", "no", "0", "n"):
        return ValidationResult(True, normalized=False)
    return ValidationResult(False, error=f"'{value}' is not a boolean")


_VALIDATORS = {
    FieldType.TEXT: _v_text,
    FieldType.ENUM: _v_enum,
    FieldType.INTEGER: _v_integer,
    FieldType.CURRENCY: _v_currency,
    FieldType.MEASUREMENT: _v_measurement,
    FieldType.LICENSE_NUMBER: _v_license,
    FieldType.DATE: _v_date,
    FieldType.BOOLEAN: _v_boolean,
}
