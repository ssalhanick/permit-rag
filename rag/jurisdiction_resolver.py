"""
rag/jurisdiction_resolver.py — Address-based jurisdiction resolution (Sprint 5 / Task 14C)
===========================================================================================
Converts a free-text address into a jurisdiction stack using:
  1. Census Bureau Geocoding API — free, no key, converts address → (lat, lng)
  2. PostGIS ST_Contains — point-in-polygon against municipal_boundaries table

Public API:
    geocode(address)                  -> GeocodedAddress | None
    resolve_jurisdiction(address)     -> JurisdictionResolution
    municipality_from_address(address) -> str | None  (simple helper for routes)

Import boundary: rag/ → db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# Census Bureau Geocoding API — free, no key required
_CENSUS_GEOCODE_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)
_CENSUS_TIMEOUT_S = 10
_CENSUS_BENCHMARK = "Public_AR_Current"


# ── Result types ─────────────────────────────────────────────


@dataclass
class GeocodedAddress:
    """Result of a Census Bureau geocode call."""

    input_address: str
    matched_address: str
    lat: float
    lng: float
    latency_ms: int


@dataclass
class JurisdictionResolution:
    """
    Full jurisdiction resolution for an address.

    jurisdiction_id — the matched municipality slug (e.g. 'dallas'), or None
    overlay_ids     — any overlay districts (flood zone, historic, etc.) — future Sprint 6
    geocode         — raw geocode result, or None if geocoding failed
    error           — human-readable failure reason, or None on success
    """

    input_address: str
    jurisdiction_id: Optional[str] = None
    overlay_ids: list[str] = field(default_factory=list)
    geocode: Optional[GeocodedAddress] = None
    error: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.jurisdiction_id is not None


# ── Geocoding ────────────────────────────────────────────────


def geocode(address: str) -> Optional[GeocodedAddress]:
    """
    Convert a free-text address to (lat, lng) via Census Bureau Geocoding API.

    Returns None if the address cannot be matched or the API is unreachable.
    """
    import requests

    params = {
        "address": address,
        "benchmark": _CENSUS_BENCHMARK,
        "format": "json",
    }

    t0 = time.perf_counter()
    try:
        resp = requests.get(_CENSUS_GEOCODE_URL, params=params, timeout=_CENSUS_TIMEOUT_S)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        log.warning("geocode: Census API request failed for %r: %s", address, exc)
        return None

    latency_ms = int((time.perf_counter() - t0) * 1000)

    matches = (
        body.get("result", {})
        .get("addressMatches", [])
    )
    if not matches:
        log.info("geocode: no match for %r (latency=%dms)", address, latency_ms)
        return None

    best = matches[0]
    coords = best.get("coordinates", {})
    lat = coords.get("y")
    lng = coords.get("x")
    if lat is None or lng is None:
        log.warning("geocode: match found but coordinates missing for %r", address)
        return None

    matched_addr = best.get("matchedAddress", address)
    log.info(
        "geocode: %r → (%.6f, %.6f) '%s' in %dms",
        address, lat, lng, matched_addr, latency_ms,
    )
    return GeocodedAddress(
        input_address=address,
        matched_address=matched_addr,
        lat=float(lat),
        lng=float(lng),
        latency_ms=latency_ms,
    )


# ── Point-in-polygon ─────────────────────────────────────────


def _point_in_polygon(lat: float, lng: float) -> Optional[str]:
    """
    Return the jurisdiction_id of the municipal boundary containing (lat, lng),
    or None if no boundary matches.

    Queries municipal_boundaries using PostGIS ST_Contains.
    """
    from db.client import get_pool

    sql = """
        SELECT mb.jurisdiction_id
        FROM municipal_boundaries mb
        WHERE ST_Contains(
            mb.geom,
            ST_SetSRID(ST_MakePoint(%s, %s), 4326)
        )
        LIMIT 1;
    """
    try:
        pool = get_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (lng, lat))   # PostGIS is (longitude, latitude)
                row = cur.fetchone()
                if row:
                    jid = row[0]
                    log.info(
                        "_point_in_polygon: (%.6f, %.6f) → '%s'", lat, lng, jid
                    )
                    return jid
    except Exception as exc:
        log.warning("_point_in_polygon: DB query failed: %s", exc)
    return None


# ── Public resolver ──────────────────────────────────────────


def resolve_jurisdiction(address: str) -> JurisdictionResolution:
    """
    Full address → jurisdiction resolution pipeline.

    Steps:
        1. Geocode address via Census Bureau API
        2. Point-in-polygon against municipal_boundaries
        3. Return JurisdictionResolution (may be unresolved if either step fails)

    Overlay district resolution (flood zones, historic districts) is a future
    Sprint 6 extension — placeholder field `overlay_ids` is always [] for now.
    """
    resolution = JurisdictionResolution(input_address=address)

    if not address or not address.strip():
        resolution.error = "Empty address provided."
        return resolution

    # Step 1: Geocode
    geo = geocode(address)
    if geo is None:
        resolution.error = (
            f"Could not geocode address: {address!r}. "
            "Verify the address format and try again."
        )
        log.info("resolve_jurisdiction: geocoding failed for %r", address)
        return resolution

    resolution.geocode = geo

    # Step 2: Point-in-polygon
    jid = _point_in_polygon(geo.lat, geo.lng)
    if jid is None:
        resolution.error = (
            f"Address geocoded to ({geo.lat:.6f}, {geo.lng:.6f}) but did not "
            "fall within any loaded municipal boundary. "
            "Currently only Dallas boundaries are loaded — see docs/backlog.md."
        )
        log.info(
            "resolve_jurisdiction: no boundary match for (%.6f, %.6f)",
            geo.lat, geo.lng,
        )
        return resolution

    resolution.jurisdiction_id = jid
    log.info(
        "resolve_jurisdiction: %r → '%s' via (%.6f, %.6f)",
        address, jid, geo.lat, geo.lng,
    )
    return resolution


def municipality_from_address(address: str) -> Optional[str]:
    """
    Convenience wrapper: return the municipality slug for an address, or None.

    Used by the query route to auto-populate `municipality` when `address` is
    provided but `municipality` is not.
    """
    if not address or not address.strip():
        return None
    resolution = resolve_jurisdiction(address)
    return resolution.jurisdiction_id
