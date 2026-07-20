import json
import os
from typing import Any
from shapely.geometry import shape, Point

# Resolve path to boundary files stored under db/gis_data/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
GIS_DATA_DIR = os.path.join(ROOT_DIR, "db", "gis_data")


def _check_district(city: str, layer_type: str, point: Point) -> str | None:
    """Helper to check if a Point falls inside any polygons in a GeoJSON file."""
    file_path = os.path.join(GIS_DATA_DIR, city, f"{layer_type}.geojson")
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        for feature in features:
            geom = shape(feature.get("geometry", {}))
            if geom.contains(point):
                name = feature.get("properties", {}).get("name")
                if isinstance(name, str):
                    return name
    except Exception:
        # Fail silently if JSON is malformed
        pass
    return None


def lookup_jurisdiction_overlays(
    municipality: str | None,
    latitude: float | None,
    longitude: float | None
) -> tuple[str | None, str | None]:
    """
    Check coordinates against local GeoJSON boundary files to resolve districts.

    Args:
        municipality: Target city name (e.g. 'Dallas')
        latitude: Latitude coordinate of the address
        longitude: Longitude coordinate of the address

    Returns:
        tuple: (historic_district_name, conservation_district_name)
    """
    if not municipality or latitude is None or longitude is None:
        return None, None

    city = municipality.strip().lower().replace(" ", "-")
    point = Point(longitude, latitude)  # Shapely Point takes (x, y) / (lng, lat)

    historic = _check_district(city, "historic_districts", point)
    conservation = _check_district(city, "conservation_districts", point)

    return historic, conservation
