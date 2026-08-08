"""
rag/jurisdiction_ids.py — jurisdiction ID spelling canonicalization.
=====================================================================
A single normalization surface for the "municipality" spelling produced by
several independent sources (the frontend Mapbox autocomplete slug, hand-typed
Settings text, a project's stored value) so they converge on the id the corpus
actually uses (``jurisdictions.id`` / ``documents.municipality``).

Confirmed real-world collision: Fort Worth's seeded id is ``fortworth`` (no
separator — generated from real ingested ``documents.municipality`` rows), but
the frontend Mapbox slug and this repo's own planning docs produce the
hyphenated ``fort-worth``. Canonicalizing on ``fortworth`` (the corpus's actual
spelling) avoids a corpus data migration; every other spelling maps onto it.

Deliberately does NOT strip hyphens in general — several real jurisdiction ids
carry a meaningful one (the county suffix, e.g. ``dallas-county``), so a
blanket punctuation-stripping slugify would silently break those.

Import boundary: standard library only (AGENTS.md) — importable from rag/,
rag/agents/, and db/-adjacent code alike without pulling in a DB dependency.
"""

from __future__ import annotations

import re

KNOWN_ALIASES: dict[str, str] = {
    "fort-worth": "fortworth",
    "fort worth": "fortworth",
    "ft-worth": "fortworth",
    "ft worth": "fortworth",
    "ftworth": "fortworth",
    # Nationwide jurisdiction resolution (rag.jurisdiction_resolver) suffixes
    # every place/county it resolves with its containing state name to avoid
    # cross-state collisions (multiple Springfields, multiple Washington
    # Counties). Dallas/Fort Worth/Plano and their counties were seeded
    # before that convention existed and have no state suffix in the corpus
    # (documents.municipality) — alias the state-suffixed forms back onto
    # the unsuffixed corpus spelling instead of migrating documents data.
    "dallas-texas": "dallas",
    "fort-worth-texas": "fortworth",
    "fort worth-texas": "fortworth",
    "ft-worth-texas": "fortworth",
    "ft worth-texas": "fortworth",
    "plano-texas": "plano",
    "dallas county-texas": "dallas-county",
    "dallas-county-texas": "dallas-county",
    "tarrant county-texas": "tarrant-county",
    "tarrant-county-texas": "tarrant-county",
    "collin county-texas": "collin-county",
    "collin-county-texas": "collin-county",
    # documents/catalog.json's first genuinely out-of-Texas entry (Fishers,
    # Indiana, added 2026-08-08) was catalogued with a bare municipality
    # slug too, before this alias existed — same fix as the DFW cities
    # above. New nationwide ingestion should prefer a state-suffixed
    # municipality value (e.g. "fishers-indiana") to match what the
    # resolver computes and avoid needing a new alias per city; add one
    # here only when an existing bare slug must be preserved.
    "fishers-indiana": "fishers",
}


def slugify(raw: str) -> str:
    """Lowercase, trim, and collapse internal whitespace runs to a hyphen.

    Existing hyphens pass through untouched.
    """
    return re.sub(r"\s+", "-", raw.strip().lower())


def canonicalize(raw: str | None) -> str | None:
    """Map a free-text municipality spelling onto its canonical jurisdiction id.

    Returns None for empty/missing input. Never raises and never rejects an
    unrecognized spelling outright — it just slugifies it — since an unknown
    jurisdiction id may be a legitimate not-yet-covered city rather than bad
    input (see ``rag.jurisdiction_resolver.validate_jurisdiction_id`` for the
    DB-backed "is this actually a known jurisdiction" check).
    """
    if not raw or not raw.strip():
        return None
    lowered = raw.strip().lower()
    if lowered in KNOWN_ALIASES:
        return KNOWN_ALIASES[lowered]
    return slugify(raw)
