"""
scripts/load_gis_boundaries.py — load a real municipal boundary polygon.
=========================================================================
Replaces the one-row, hand-drawn Dallas "pilot envelope" in
`municipal_boundaries` (db/seeds/municipal_boundaries.sql) with real city/
county/state polygons, and loads the cities docs/backlog.md already names
sources for but nobody has loaded yet (Plano, Fort Worth, ...).

Deliberately uses only already-installed dependencies (shapely, requests) —
no GDAL/fiona/geopandas/pyproj. Two input modes, both already-WGS84 GeoJSON,
so no reprojection code is needed:

    --geojson <path-or-url>       a plain GeoJSON Feature/FeatureCollection
    --arcgis-query <layer-url>    an ArcGIS FeatureServer/MapServer *layer*
                                  URL (e.g. ".../MapServer/0"); this script
                                  appends /query?...&f=geojson&outSR=4326

Target-safe via scripts/_db_target (this repo's rule: never a bare
bootstrap_env). Requires the jurisdiction_id to already have a row in
`jurisdictions` — this script only loads geometry, never creates a
jurisdiction.

Examples:
    py scripts/load_gis_boundaries.py dallas \\
        --arcgis-query https://gis.dallascityhall.com/sharedmaps/rest/services/basemap/CityBoundary/MapServer/0 \\
        --dry-run

    py scripts/load_gis_boundaries.py dallas \\
        --arcgis-query https://gis.dallascityhall.com/sharedmaps/rest/services/basemap/CityBoundary/MapServer/0 \\
        --validate-address "1500 Marilla St, Dallas, TX" --local
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

_UPSERT_SQL = """
    INSERT INTO municipal_boundaries
        (jurisdiction_id, boundary_name, source_name, source_url, geom)
    VALUES (
        %(jurisdiction_id)s, %(boundary_name)s, %(source_name)s, %(source_url)s,
        ST_Multi(ST_GeomFromText(%(wkt)s, 4326))
    )
    ON CONFLICT (jurisdiction_id) DO UPDATE SET
        boundary_name = EXCLUDED.boundary_name,
        source_name   = EXCLUDED.source_name,
        source_url    = EXCLUDED.source_url,
        geom          = EXCLUDED.geom,
        loaded_at     = NOW();
"""


def _fetch_geojson(*, geojson: str | None, arcgis_query: str | None) -> dict[str, Any]:
    """Fetch GeoJSON from a local path, a raw URL, or an ArcGIS layer query."""
    import requests

    if arcgis_query:
        resp = requests.get(
            f"{arcgis_query.rstrip('/')}/query",
            params={"where": "1=1", "outFields": "*", "f": "geojson", "outSR": "4326"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    assert geojson is not None
    if geojson.startswith("http://") or geojson.startswith("https://"):
        resp = requests.get(geojson, timeout=30)
        resp.raise_for_status()
        return resp.json()
    return __import__("json").loads(Path(geojson).read_text(encoding="utf-8"))


def parse_boundary_geometry(data: dict[str, Any]):
    """Union every feature's geometry into one MultiPolygon.

    Raises ValueError on empty/malformed input rather than silently loading a
    partial or empty boundary.
    """
    from shapely.geometry import MultiPolygon, shape
    from shapely.ops import unary_union

    features = data.get("features")
    if not features:
        raise ValueError("GeoJSON has no features")
    geoms = [shape(f["geometry"]) for f in features if f.get("geometry")]
    if not geoms:
        raise ValueError("No feature in the GeoJSON had a geometry")

    merged = unary_union(geoms)
    if merged.geom_type == "Polygon":
        merged = MultiPolygon([merged])
    elif merged.geom_type != "MultiPolygon":
        raise ValueError(
            f"Unexpected merged geometry type {merged.geom_type!r} — expected "
            "Polygon or MultiPolygon boundary data."
        )
    return merged


def _validate_address_against_geometry(address: str, geometry) -> bool:
    """Geocode `address` (free Census API) and check it falls inside `geometry`.

    Checked directly against the in-memory geometry (not the DB), so this works
    in --dry-run mode too, as a pre-write sanity check.
    """
    from shapely.geometry import Point

    from rag.jurisdiction_resolver import geocode

    geocoded = geocode(address)
    if geocoded is None:
        print(f"  Could not geocode {address!r} — cannot validate.")
        return False
    point = Point(geocoded.lng, geocoded.lat)
    inside = geometry.contains(point)
    print(
        f"  {address!r} -> ({geocoded.lat:.6f}, {geocoded.lng:.6f}) "
        f"[{geocoded.matched_address}] -> {'INSIDE' if inside else 'OUTSIDE'} the boundary"
    )
    return inside


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jurisdiction_id", help="Must already exist in the jurisdictions table")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--geojson", help="Local path or URL to a GeoJSON file")
    source.add_argument("--arcgis-query", help="ArcGIS FeatureServer/MapServer *layer* URL")
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only, no DB write")
    parser.add_argument("--validate-address", help="Geocode this address and check it falls inside the loaded boundary")
    args, _unknown = parser.parse_known_args()  # --local / --database-url handled by _db_target below

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=args.dry_run)

    print(f"Fetching boundary data for jurisdiction_id={args.jurisdiction_id!r}...")
    data = _fetch_geojson(geojson=args.geojson, arcgis_query=args.arcgis_query)
    feature_count = len(data.get("features", []))
    geometry = parse_boundary_geometry(data)
    centroid = geometry.centroid
    print(
        f"  Parsed {feature_count} feature(s) -> merged {geometry.geom_type}, "
        f"centroid=({centroid.y:.6f}, {centroid.x:.6f}), area~={geometry.area:.6f} deg^2"
    )

    if args.validate_address:
        _validate_address_against_geometry(args.validate_address, geometry)

    if args.dry_run:
        print("\n--dry-run: no database write performed.")
        return 0

    _db_target.ensure_reachable(target)
    from db.client import get_conn, get_jurisdiction

    jurisdiction = get_jurisdiction(args.jurisdiction_id)
    if jurisdiction is None:
        print(
            f"\nNo jurisdictions row for {args.jurisdiction_id!r} — add it to "
            "db/seeds/jurisdictions.sql first. This script only loads geometry, "
            "never creates a jurisdiction."
        )
        return 1

    source_name = args.arcgis_query or args.geojson
    params = {
        "jurisdiction_id": args.jurisdiction_id,
        "boundary_name": f"{jurisdiction['name']} (load_gis_boundaries.py)",
        "source_name": source_name,
        "source_url": source_name if str(source_name).startswith("http") else None,
        "wkt": geometry.wkt,
    }
    with get_conn() as conn:
        conn.execute(_UPSERT_SQL, params)
        conn.commit()

    print(f"\n✓ Loaded boundary for {args.jurisdiction_id!r} ({jurisdiction['name']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
