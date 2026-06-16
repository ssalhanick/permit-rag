# permit_rag — Backlog

Items that are explicitly deferred from current sprints. Each item has a rationale,
a blocking condition, and suggested sprint target.

---

## 🗺️ GIS: Municipal Boundary Expansion

**Context:** Sprint 4 loaded the Dallas municipal boundary into `municipal_boundaries`
and validated point-in-polygon via PostGIS `ST_Contains`. The geocoding resolver
(Sprint 5, Task 14C) will auto-detect jurisdiction from an address — but only for
Dallas until additional boundaries are loaded.

**Decision:** Defer boundary loading for other cities until Sprint 5 is closed.
Track each city below.

### DFW Cities — Boundary Load Status

| City | Jurisdiction ID | Open Data Source | Status |
|------|----------------|-----------------|--------|
| Dallas | `dallas` | [Dallas Open Data GeoHub](https://gis.dallascityhall.com/sharedmaps/rest/services/basemap/CityBoundary/MapServer) | ✅ Loaded (Sprint 4) |
| Plano | `plano` | [Plano Open Data](https://data.plano.gov/datasets/city-limits) | ⬜ Pending |
| Fort Worth | `fort-worth` | [Fort Worth Open Data](https://data.fortworthtexas.gov/datasets/city-limits) | ⬜ Pending |
| Arlington | `arlington` | [Arlington GIS](https://gis.arlingtontx.gov/) | ⬜ Pending |
| Frisco | `frisco` | [Frisco Open Data](https://data.frisco.gov/datasets/city-limits) | ⬜ Pending |
| McKinney | `mckinney` | [McKinney Open Data](https://data.mckinneytexas.gov/) | ⬜ Pending |
| Irving | `irving` | [Irving GIS Services](https://www.irvingbuildingservices.net/gis) | ⬜ Pending |
| Garland | `garland` | [Garland Open Data](https://data.garlandtx.gov/) | ⬜ Pending |
| Denton | `denton` | [Denton Open Data](https://data.cityofdenton.com/) | ⬜ Pending |
| Allen | `allen` | [Allen GIS](https://www.cityofallen.org/181/GIS) | ⬜ Pending |

### Overlay Districts (future Sprint 6+)

| Layer | Source | Status |
|-------|--------|--------|
| FEMA Flood Zones (SFHA) | [FEMA NFHL REST API](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer) | ⬜ Pending |
| Dallas Historic Districts | [Texas Historical Commission GIS](https://atlas.thc.texas.gov/) | ⬜ Pending |
| Dallas Planned Development Overlays | [Dallas Zoning Explorer](https://gis.dallascityhall.com/) | ⬜ Pending |

### Load Script Notes

The Sprint 5 `scripts/load_gis_boundaries.py` script should be extended (not replaced)
for each new city. Pattern per city:
1. Download shapefile or GeoJSON from the open data portal above
2. Reproject to EPSG:4326 if needed
3. Insert into `municipal_boundaries` (jurisdiction_id, boundary_name, source_name, source_url, geom)
4. Validate with point-in-polygon test against a known address

### Blocking Condition for Google Maps Upgrade

- Address autocomplete is currently powered by **Mapbox Search API** (free tier).
- When the LLC is established and a Google Cloud account is created, swap to
  **Google Places Autocomplete API** by:
  1. Getting a Maps Platform API key with Places API enabled
  2. Setting `VITE_MAPBOX_TOKEN` → `VITE_GOOGLE_MAPS_API_KEY` in `.env`
  3. Replacing the `AddressAutocomplete` component fetch URL

---

## 🔍 Retrieval: BM25 Hybrid A/B Eval

**Context:** `RETRIEVAL_HYBRID_ENABLED` defaults to `False`. The architecture review
identified enabling hybrid search as the highest-leverage lever for improving context
precision (currently 0.624).

**Decision:** Defer to Sprint 6. After Sprint 5 Fixes 1+3 land, run a dedicated A/B
eval (dense-only vs. hybrid) and flip the default if hybrid wins.

**Blocking condition:** Fix 1 (SQL ordering) must be live before the A/B eval to
ensure the dense baseline is clean.

---

## 📊 Evaluation: Relevancy Improvement (Fix 2)

**Context:** Relevancy is 0.694 (weakest metric). Fix 2 (citation-aware chunk filtering
in `POST /query/answer`) is deferred to Sprint 6 per the integration plan — it depends
on Fix 3 (citation regex hardening) being live first.

---

*Last updated: Sprint 5 start · 2026-06-16*
