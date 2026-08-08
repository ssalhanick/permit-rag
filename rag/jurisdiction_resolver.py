"""
rag/jurisdiction_resolver.py — Address-based jurisdiction resolution
======================================================================
Converts a free-text address into a jurisdiction stack using:
  1. Census Bureau Geocoding API — free, no key, converts address → (lat, lng)
  2. Local override table — PostGIS ST_Contains against municipal_boundaries,
     a small, hand-loaded set of higher-precision polygons (ETJs, annexation
     corrections) for the handful of cities where that matters.
  3. Nationwide fallback — the Census Bureau's own `geographies` lookup,
     which resolves a point to its containing incorporated place/county/state
     directly from the same authoritative TIGER/Line data, server-side, with
     no local polygon data to load or maintain. A miss on the incorporated
     place degrades one level to the containing county (unincorporated
     areas), rather than failing resolution outright.

Nationwide resolution deliberately doesn't require every jurisdiction to have
real documents ingested — db.client.get_jurisdiction_chain() widens a query
to county/state/federal content, and the grounding gate
(rag/agents/manager.py::_grounding_verdict, `jurisdiction_mismatch`) abstains
rather than answering confidently wrong when retrieved chunks aren't actually
the resolved jurisdiction's own content.

Public API:
    geocode(address)                     -> GeocodedAddress | None
    resolve_jurisdiction_for_point(lat, lng) -> str | None
    resolve_jurisdiction(address)        -> JurisdictionResolution
    municipality_from_address(address)   -> str | None  (simple helper for routes)

Import boundary: rag/ → db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Census Bureau Geocoding API — free, no key required
_CENSUS_GEOCODE_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
)
_CENSUS_GEOGRAPHIES_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/coordinates"
)
_CENSUS_TIMEOUT_S = 10
_CENSUS_BENCHMARK = "Public_AR_Current"
_CENSUS_VINTAGE = "Current_Current"
_CENSUS_RETRIES = 2
_CENSUS_RETRY_DELAY_S = 0.5

# In-process cache for geographies lookups, keyed on rounded (lat, lng)
# (~5 decimals ≈ 1m precision). Municipal/county/state boundaries change
# rarely, so a multi-week TTL is safe; this is process-local, not shared
# across workers — fine for now, revisit as a DB-backed cache if lookup
# volume ever makes that worthwhile.
_GEOGRAPHY_CACHE_TTL_S = 60 * 60 * 24 * 30
_geography_cache: dict[tuple[float, float], tuple[float, GeographyMatch | None]] = {}


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
class GeographyMatch:
    """Result of a Census Bureau `geographies` lookup for one point.

    Any field may be None — e.g. a point outside any incorporated place has
    place_name=None, county_name still set; a point outside the US has all
    three as None.
    """

    place_name: str | None
    county_name: str | None
    state_name: str | None
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
    jurisdiction_id: str | None = None
    overlay_ids: list[str] = field(default_factory=list)
    geocode: GeocodedAddress | None = None
    error: str | None = None

    @property
    def resolved(self) -> bool:
        return self.jurisdiction_id is not None


# ── Geocoding ────────────────────────────────────────────────


def _census_get(
    url: str, params: dict, *, context: str, retries: int = _CENSUS_RETRIES
) -> dict | None:
    """
    GET one of the Census Bureau's free geocoder endpoints, with a short
    retry-with-backoff for transient failures — it's a free, non-SLA-backed
    public service, so a single hiccup shouldn't be treated as permanent.

    Returns the parsed JSON body, or None if every attempt failed.
    """
    import requests

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=_CENSUS_TIMEOUT_S)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(_CENSUS_RETRY_DELAY_S)
    log.warning(
        "%s: Census API request failed after %d attempt(s): %s",
        context, retries, last_exc,
    )
    return None


def geocode(address: str) -> GeocodedAddress | None:
    """
    Convert a free-text address to (lat, lng) via Census Bureau Geocoding API.

    Returns None if the address cannot be matched or the API is unreachable.
    """
    params = {
        "address": address,
        "benchmark": _CENSUS_BENCHMARK,
        "format": "json",
    }

    t0 = time.perf_counter()
    body = _census_get(_CENSUS_GEOCODE_URL, params, context=f"geocode({address!r})")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    if body is None:
        return None

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


def _point_in_polygon(lat: float, lng: float) -> str | None:
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
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (lng, lat))   # PostGIS is (longitude, latitude)
            row = cur.fetchone()
            if row:
                jid = row["jurisdiction_id"]
                log.info(
                    "_point_in_polygon: (%.6f, %.6f) → '%s'", lat, lng, jid
                )
                return jid
    except Exception as exc:
        log.warning("_point_in_polygon: DB query failed: %s", exc)
    return None


# ── Nationwide fallback (Census `geographies` lookup) ─────────


def _geographies_for_point(lat: float, lng: float) -> GeographyMatch | None:
    """
    Resolve (lat, lng) to its containing incorporated place/county/state via
    the Census Bureau's `geographies` endpoint — the same TIGER/Line data
    backing the geocoder, matched server-side, so no local polygon table is
    needed for nationwide coverage.

    Cached in-process for _GEOGRAPHY_CACHE_TTL_S; failures are not cached, so
    a transient outage doesn't wedge every subsequent lookup for the point.
    """
    cache_key = (round(lat, 5), round(lng, 5))
    cached = _geography_cache.get(cache_key)
    if cached is not None:
        expiry, result = cached
        if time.monotonic() < expiry:
            return result
        del _geography_cache[cache_key]

    params = {
        "x": lng,
        "y": lat,
        "benchmark": _CENSUS_BENCHMARK,
        "vintage": _CENSUS_VINTAGE,
        "format": "json",
    }
    t0 = time.perf_counter()
    body = _census_get(
        _CENSUS_GEOGRAPHIES_URL, params,
        context=f"_geographies_for_point({lat:.6f},{lng:.6f})",
    )
    if body is None:
        return None
    latency_ms = int((time.perf_counter() - t0) * 1000)

    geographies = body.get("result", {}).get("geographies", {})
    places = geographies.get("Incorporated Places") or []
    counties = geographies.get("Counties") or []
    states = geographies.get("States") or []

    state_name = states[0].get("NAME") if states else None
    county_name = counties[0].get("NAME") if counties else None
    place = places[0] if places else None
    place_name = (place.get("BASENAME") or place.get("NAME")) if place else None

    result = GeographyMatch(
        place_name=place_name, county_name=county_name, state_name=state_name,
        latency_ms=latency_ms,
    )
    _geography_cache[cache_key] = (time.monotonic() + _GEOGRAPHY_CACHE_TTL_S, result)
    log.info(
        "_geographies_for_point: (%.6f, %.6f) → place=%r county=%r state=%r",
        lat, lng, place_name, county_name, state_name,
    )
    return result


def _resolve_via_geographies(lat: float, lng: float) -> str | None:
    """
    Nationwide fallback: resolve (lat, lng) to a jurisdiction_id via the
    Census `geographies` lookup, lazily creating county/city rows in
    `jurisdictions` as new places are encountered (states/counties are
    normally pre-seeded — see scripts/seed_states_counties.py — but a
    missing county is filled in here too so resolution self-heals rather
    than depending on the seed having run first).

    Every candidate id is suffixed with its containing state before
    canonicalization (e.g. "springfield-illinois") to avoid cross-state name
    collisions; jurisdiction_ids.KNOWN_ALIASES maps the handful of ids seeded
    before this convention existed (dallas, fortworth, plano and their
    counties) back onto their unsuffixed corpus spelling.

    Falls back one level to the county when there's no incorporated place
    (unincorporated areas) — this is a correctness improvement over silent
    failure, not a new edge case to work around. Returns None only when
    Census has no county/state for the point at all (e.g. outside the US).
    """
    geo = _geographies_for_point(lat, lng)
    if geo is None or geo.state_name is None:
        return None

    from db.client import get_jurisdiction, upsert_jurisdiction
    from rag.jurisdiction_ids import canonicalize

    state_id = canonicalize(geo.state_name)

    county_id = None
    if geo.county_name:
        county_id = canonicalize(f"{geo.county_name}-{geo.state_name}")
        if county_id and get_jurisdiction(county_id) is None:
            upsert_jurisdiction(
                id=county_id,
                name=f"{geo.county_name}, {geo.state_name}",
                level="county",
                parent_id=state_id,
            )

    if geo.place_name:
        place_id = canonicalize(f"{geo.place_name}-{geo.state_name}")
        if place_id and get_jurisdiction(place_id) is None:
            upsert_jurisdiction(
                id=place_id,
                name=f"City of {geo.place_name}",
                level="city",
                parent_id=county_id or state_id,
            )
        return place_id

    return county_id


def resolve_jurisdiction_for_point(lat: float, lng: float) -> str | None:
    """
    Resolve (lat, lng) to a jurisdiction_id: the local override table first
    (a small set of hand-loaded, higher-precision polygons), then the
    nationwide Census `geographies` fallback. Returns None if neither
    resolves — e.g. the point is outside the US.
    """
    jid = _point_in_polygon(lat, lng)
    if jid is not None:
        return jid
    return _resolve_via_geographies(lat, lng)


# ── Public resolver ──────────────────────────────────────────


def resolve_jurisdiction(address: str) -> JurisdictionResolution:
    """
    Full address → jurisdiction resolution pipeline.

    Steps:
        1. Geocode address via Census Bureau API
        2. resolve_jurisdiction_for_point: local override table, then the
           nationwide Census `geographies` fallback
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

    # Step 2: local override table, then nationwide fallback
    jid = resolve_jurisdiction_for_point(geo.lat, geo.lng)
    if jid is None:
        resolution.error = (
            f"Address geocoded to ({geo.lat:.6f}, {geo.lng:.6f}) but could not "
            "be resolved to a known city or county. It may be outside the US, "
            "or in an area the Census Bureau's boundary data doesn't cover."
        )
        log.info(
            "resolve_jurisdiction: no jurisdiction match for (%.6f, %.6f)",
            geo.lat, geo.lng,
        )
        return resolution

    resolution.jurisdiction_id = jid
    log.info(
        "resolve_jurisdiction: %r → '%s' via (%.6f, %.6f)",
        address, jid, geo.lat, geo.lng,
    )
    return resolution


def municipality_from_address(address: str) -> str | None:
    """
    Convenience wrapper: return the municipality slug for an address, or None.

    Used by the query route to auto-populate `municipality` when `address` is
    provided but `municipality` is not.
    """
    if not address or not address.strip():
        return None
    resolution = resolve_jurisdiction(address)
    return resolution.jurisdiction_id


# ── Client-supplied jurisdiction validation ───────────────────


def validate_jurisdiction_id(raw: str | None) -> tuple[str | None, str | None]:
    """
    Canonicalize a client-supplied municipality spelling and confirm it's known.

    Returns (jurisdiction_id, None) once canonicalized, if that id has a row in
    `jurisdictions` — or (None, error) if not. Does NOT reject an unrecognized
    id as invalid: db/seeds/jurisdictions.sql's own comment lists several DFW
    cities as legitimate future jurisdictions ("add when corpus documents are
    ingested"), so creating a project for one of those today is expected, not
    a bad request. Callers decide what to do with an unknown result — e.g.
    rag.coverage turns it into a user-facing "outside coverage" signal.
    """
    from db.client import get_jurisdiction
    from rag.jurisdiction_ids import canonicalize

    candidate = canonicalize(raw)
    if candidate is None:
        return None, "no municipality provided"
    if get_jurisdiction(candidate) is None:
        return None, f"unknown jurisdiction: {candidate!r}"
    return candidate, None
