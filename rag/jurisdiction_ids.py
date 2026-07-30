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
