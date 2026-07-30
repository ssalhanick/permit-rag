"""
rag/coverage.py — deterministic "is this address in our coverage area?" check.
================================================================================
Distinct from the generic low-confidence retrieval abstain: that's a soft
grounding-floor signal that doesn't distinguish "wrong jurisdiction" from
"right jurisdiction, obscure topic." This module answers a narrower, factual
question directly: does the resolved municipality have any real documents, or
does the address not fall inside any loaded boundary at all.

Import boundary: rag/ -> db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass

# Fallback used only if the DB is unreachable when building a fallback message
# (rag/generator.py) — real corpus coverage as of Phase 1/2 of the jurisdiction
# accuracy work. Not used for the coverage check itself, which always queries
# the DB directly rather than trusting a hardcoded list.
_STATIC_FALLBACK_CITIES = ["Dallas", "Plano", "Fort Worth"]


@dataclass(frozen=True)
class CoverageResult:
    """The outcome of a coverage check for one project/query."""

    status: str  # "covered" | "no_documents" | "no_boundary_data" | "unresolved"
    municipality: str | None
    message: str

    @property
    def is_covered(self) -> bool:
        return self.status == "covered"


def _has_active_documents(municipality: str) -> bool:
    from db.client import list_documents

    return len(list_documents(municipality=municipality, status="active")) > 0


def check_coverage(
    *,
    municipality: str | None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> CoverageResult:
    """
    Determine whether a project/query is inside the supported coverage area.

    - municipality given: covered if it has >=1 active document, else
      "no_documents" (a real, seeded jurisdiction with nothing ingested yet —
      e.g. Frisco/McKinney today).
    - No municipality but lat/lng given: point-in-polygon against loaded
      municipal boundaries. A miss is "no_boundary_data", not "unsupported" —
      it may just be a city Phase 2 of the GIS rollout hasn't loaded yet.
    - Neither given: "unresolved" — nothing to check yet, not a warning.
    """
    if municipality:
        if _has_active_documents(municipality):
            return CoverageResult("covered", municipality, "This area is in our coverage area.")
        return CoverageResult(
            "no_documents",
            municipality,
            f"We don't yet have {municipality} ordinance documents in our coverage area. "
            "You can petition to have this jurisdiction added.",
        )

    if latitude is not None and longitude is not None:
        from rag.jurisdiction_resolver import _point_in_polygon

        resolved = _point_in_polygon(latitude, longitude)
        if resolved:
            return check_coverage(municipality=resolved)
        return CoverageResult(
            "no_boundary_data",
            None,
            "This address doesn't fall inside any jurisdiction boundary we've loaded yet. "
            "It may still be in our coverage area — we just haven't loaded that city's "
            "boundary data. You can petition to have this area added.",
        )

    return CoverageResult("unresolved", None, "No address on file yet.")


def covered_municipalities() -> list[str]:
    """City display names with >=1 active document (e.g. "Dallas", "Fort Worth").

    Falls back to a small static, known-accurate list if the DB is unreachable
    (e.g. rag/generator.py building a fallback message with no DB in this
    request path) rather than raising or showing an empty list to the user.
    """
    try:
        from db.client import list_covered_municipalities

        cities = [
            row["name"].removeprefix("City of ") for row in list_covered_municipalities()
        ]
        return cities or list(_STATIC_FALLBACK_CITIES)
    except Exception:
        return list(_STATIC_FALLBACK_CITIES)
