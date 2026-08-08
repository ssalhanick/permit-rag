"""
scripts/seed_states_counties.py — seed all 50 states + DC and ~3,143 counties.
================================================================================
Nationwide jurisdiction resolution (rag/jurisdiction_resolver.py) needs a
`jurisdictions` row for every state/county so db.client.get_jurisdiction_chain()
can walk city -> county -> state -> federal instead of degrading to an
exact-match-only filter. Cities stay lazily created on first resolution (see
rag.jurisdiction_resolver._resolve_via_geographies) — pre-seeding ~19k empty
city rows would add nothing the chain-walk needs.

Source: the Census Bureau's own plain-text reference lists (not TIGER
shapefiles — no polygon data here, just names/FIPS/parent state), matching
scripts/load_gis_boundaries.py's dependency discipline (requests only, no
GDAL/fiona/geopandas/pyproj):
    States:    https://www2.census.gov/geo/docs/reference/state.txt
    Counties:  https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt

Territories (AS, GU, MP, PR, VI) are explicitly skipped — out of scope per
the nationwide jurisdiction resolution design (Census TIGER/geocoder coverage
there is inconsistent).

Every id is canonicalized through rag.jurisdiction_ids.canonicalize() before
insert, so this converges onto the three counties already seeded by hand
(dallas-county, tarrant-county, collin-county) via their KNOWN_ALIASES
entries, rather than creating duplicate state-suffixed rows for them.
ON CONFLICT DO NOTHING (db.client.upsert_jurisdiction) — never overwrites a
row a human has since curated with dept_name/dept_url.

Target-safe via scripts/_db_target (this repo's rule: never a bare
bootstrap_env).

Usage:
    py scripts/seed_states_counties.py --dry-run
    py scripts/seed_states_counties.py --local
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse

import _db_target

from api.load_env import bootstrap_env

_STATE_REFERENCE_URL = "https://www2.census.gov/geo/docs/reference/state.txt"
_COUNTY_REFERENCE_URL = (
    "https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt"
)

# Postal abbreviations for US territories — out of scope (see module docstring).
_TERRITORY_ABBRS = {"AS", "GU", "MP", "PR", "VI"}


def _fetch_lines(url: str) -> list[str]:
    import requests

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text.splitlines()


def fetch_states() -> list[dict[str, str]]:
    """Parse state.txt (pipe-delimited: STATE|STUSAB|STATE_NAME|STATENS).

    Returns rows for the 50 states + DC only, territories excluded.
    """
    lines = _fetch_lines(_STATE_REFERENCE_URL)
    header, *rows = lines
    cols = header.strip().split("|")
    states = []
    for line in rows:
        if not line.strip():
            continue
        values = line.strip().split("|")
        row = dict(zip(cols, values, strict=False))
        if row.get("STUSAB") in _TERRITORY_ABBRS:
            continue
        states.append(row)
    return states


def fetch_counties() -> list[dict[str, str]]:
    """Parse national_county2020.txt (pipe-delimited:
    STATE|STATEFP|COUNTYFP|COUNTYNAME|CLASSFP).

    Returns rows for counties in the 50 states + DC only.
    """
    lines = _fetch_lines(_COUNTY_REFERENCE_URL)
    header, *rows = lines
    cols = header.strip().split("|")
    counties = []
    for line in rows:
        if not line.strip():
            continue
        values = line.strip().split("|")
        row = dict(zip(cols, values, strict=False))
        if row.get("STATE") in _TERRITORY_ABBRS:
            continue
        counties.append(row)
    return counties


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse only, no DB write")
    args, _unknown = parser.parse_known_args()  # --local / --database-url handled by _db_target below

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=args.dry_run)

    print("Fetching state reference list...")
    states = fetch_states()
    print(f"  {len(states)} states/DC (territories excluded)")

    print("Fetching county reference list...")
    counties = fetch_counties()
    print(f"  {len(counties)} counties")

    from rag.jurisdiction_ids import canonicalize

    state_name_by_abbr: dict[str, str] = {}
    state_rows: list[dict[str, str]] = []
    for row in states:
        state_name = row["STATE_NAME"]
        state_id = canonicalize(state_name)
        if state_id is None:
            print(f"  WARNING: could not canonicalize state name {state_name!r}, skipping")
            continue
        state_name_by_abbr[row["STUSAB"]] = state_name
        state_rows.append({
            "id": state_id,
            "name": state_name if state_name == "District of Columbia" else f"State of {state_name}",
            "level": "state",
            "parent_id": "federal",
        })

    county_rows: list[dict[str, str]] = []
    skipped = 0
    for row in counties:
        state_name = state_name_by_abbr.get(row["STATE"])
        if state_name is None:
            skipped += 1
            continue
        county_name = row["COUNTYNAME"]
        state_id = canonicalize(state_name)
        county_id = canonicalize(f"{county_name}-{state_name}")
        if county_id is None:
            skipped += 1
            continue
        county_rows.append({
            "id": county_id,
            "name": f"{county_name}, {state_name}",
            "level": "county",
            "parent_id": state_id,
        })

    print(f"\nPrepared {len(state_rows)} state row(s), {len(county_rows)} county row(s)"
          f" ({skipped} county row(s) skipped — unmapped state).")
    print("Sample:")
    for row in state_rows[:3] + county_rows[:3]:
        print(f"  {row}")

    if args.dry_run:
        print("\n--dry-run: no database write performed.")
        return 0

    _db_target.ensure_reachable(target)
    from db.client import upsert_jurisdiction

    inserted = 0
    for row in state_rows + county_rows:
        if upsert_jurisdiction(
            id=row["id"], name=row["name"], level=row["level"], parent_id=row["parent_id"],
        ):
            inserted += 1

    print(f"\n✓ Inserted {inserted} new jurisdiction row(s) "
          f"({len(state_rows) + len(county_rows) - inserted} already existed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
