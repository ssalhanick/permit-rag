# Jurisdiction Accuracy & GIS Coverage — Runbook

Purpose: fix the remaining causes of inaccurate/"stuck" jurisdiction assignment and
build toward real local/state/federal boundary checking, historic/conservation
district detection, and a petition workflow for out-of-coverage areas.

**Run this on the machine with the real corpus and database** — this machine's DB
is empty, so none of the migration/loader/RAGAs steps below can be executed or
verified here. Before any step that touches a database, confirm the target with
`scripts/_db_target.py`'s banner (read the Target + Source lines every time — see
the DB-target-drift note at the end of this file).

## Status

| Phase | What it fixes | Status |
|---|---|---|
| 0 | `res.municipality` bug + address-change re-resolve | ✅ Done — see `api/routes/projects.py`, `tests/test_project_jurisdiction_routes.py` |
| 1 | Jurisdiction ID canonicalization + local/state/federal hierarchy in retrieval | ✅ Code done, migration **not yet applied** — see below |
| 2 | Real municipal boundary polygons (Dallas/Plano/Fort Worth + counties/state) | ✅ Loader script done, **no real boundaries loaded yet** (needs the corpus machine) |
| 3 | Deterministic "outside coverage area" warning | ✅ Done |
| 4 | Project-level historic/conservation/HOA document upload + petition system | ✅ Code done, migration **not yet applied** — see below |
| 5 | Fix false Frisco/McKinney coverage claims in docs/copy | ✅ Done |

**Implementation status as of this pass**: all application code for Phases 0–5 is
written and unit-tested on this machine (this machine's DB is empty — no corpus,
no way to apply a migration or load real boundaries here). 662 tests pass,
`ruff`/frontend build are clean. **Two things still require the corpus machine
before any of this is live**: applying migrations `037` and `038`, and actually
running the Phase 2 loader per city. Do these in order — Phase 1's migration
before Phase 2's loader (it assigns boundaries to canonical IDs) — and follow each
phase's verification steps below, especially the mandatory RAGAs re-run after
migration `037`.

⚠ **Do not push straight to `deployment/sites`** for the Phase 1 migration without
completing its RAGAs verification first — this repo auto-deploys to AWS on every
push to that branch (`.github/workflows/deploy.yml`), and `AGENTS.md`'s retrieval
rule exists precisely to gate this kind of change.

---

## Background — what's actually wrong today

Three independent, confirmed root causes (all verified by direct file reads, not
just static analysis):

1. **`api/routes/projects.py`'s address-only auto-resolve was silently broken**
   (now fixed in Phase 0) — it read a `.municipality` attribute that never existed
   on `JurisdictionResolution`, raised `AttributeError`, and a bare `except` ate it.
2. **A project's jurisdiction, once set, was never re-derived** — editing a
   project's address in Settings didn't re-run geocoding at all, because the only
   re-resolve trigger was an explicit `latitude`/`longitude` in the same request,
   which the Settings UI never sends. (Also fixed in Phase 0.)
3. **Boundary data is a near-total stub.** `municipal_boundaries` has exactly one
   row: a coarse, explicitly-non-production Dallas "pilot envelope" — large enough
   to overlap parts of Plano/Irving/Garland. Plano and Fort Worth, which have real
   corpus documents, have zero boundary polygons. This is the actual reason
   addresses "don't seem to be checked" against real city/county/state boundaries —
   the resolver code is correct, the underlying map data mostly doesn't exist yet.

Separately, and independent of the above: **Frisco and McKinney are advertised as
covered** (`AGENTS.md`, `README.md`, the app's own low-confidence fallback message)
**but have zero real ingested documents** — their only source files are Municode
redirect pages that fail text extraction and are hard-skipped at ingest time
(`scripts/ingest_documents.py`'s `SKIP_DOC_IDS`). Real working coverage today is
Dallas + Plano + Fort Worth + Texas (state) + federal.

No paid geocoding service is needed anywhere below. `rag/jurisdiction_resolver.py`
already uses the free, keyless Census Bureau Geocoding API + a real PostGIS
point-in-polygon check — the gap is boundary **data**, not an API.

---

## Phase 1 — Canonicalize jurisdiction IDs + hierarchy-aware retrieval

### The problem this fixes

There are **four** independent places that produce a "municipality" spelling, with
no shared validation:
1. Frontend Mapbox autocomplete slug (`frontend/src/components/AddressAutocomplete.jsx`) — produces `fort-worth` (hyphenated).
2. The server-side resolver (`rag/jurisdiction_resolver.py`) — returns whatever
   `jurisdiction_id` is stored in `municipal_boundaries`.
3. The hand-typed free-text "Municipality" field in Project Settings — anything a
   user types, unvalidated.
4. `rag/agents/prompt_router.py`'s `_JURISDICTION_ALIASES` table — maps spellings
   onto prompt-fragment filenames. **Confirmed bug**: this table has `"ftworth"`
   (abbreviated, no separator) but not `"fortworth"` (the actual seeded
   `jurisdictions.id`, full word, no separator — a genuinely different string).
   Since `_normalise_jurisdiction("fortworth")` falls through to a no-op
   `.replace(" ", "_").replace("-", "_")`, **Fort Worth's own prompt fragment is
   currently unreachable via its real, corpus-canonical ID.**

`db/seeds/jurisdictions.sql`'s own header comment says it was generated via
`SELECT DISTINCT municipality, authority_level FROM documents` — meaning
`fortworth` (no hyphen) is almost certainly the literal value already sitting on
every real ingested Fort Worth `documents.municipality` row. **Canonicalize on
`fortworth`**, not `fort-worth` (docs/backlog.md's spelling) — lower blast radius,
zero corpus data migration needed.

Additionally, `jurisdictions.parent_id` (city → county → state → federal) has been
defined since Sprint 5 but is **never walked in any application code** — retrieval
(`match_chunks` SQL) does strict equality on a single municipality string, so a
city-scoped query excludes county/state/federal documents rather than including
them alongside. This is the fix for "not checked against local/state/federal."

### Implementation

**New `rag/jurisdiction_ids.py`** (stdlib only):
```python
def slugify(raw: str) -> str:
    """Lowercase, trim, collapse whitespace/punctuation to a bare slug."""

KNOWN_ALIASES: dict[str, str] = {
    "fort-worth": "fortworth", "fort worth": "fortworth",
    "ft-worth": "fortworth", "ft worth": "fortworth", "ftworth": "fortworth",
}

def canonicalize(raw: str | None) -> str | None:
    """slugify(raw), then resolve through KNOWN_ALIASES."""
```

**`rag/jurisdiction_resolver.py`** gains (this file already imports `db.client`,
so the boundary is fine here):
```python
def validate_jurisdiction_id(raw: str | None) -> tuple[str | None, str | None]:
    """canonicalize(raw), then check it against db_client.get_jurisdiction().

    Returns (candidate, None) if known, (None, "unknown jurisdiction: ...") if not.
    Do NOT hard-reject unknown values — jurisdictions.sql's own comment lists
    Arlington/Frisco/McKinney/Irving/Garland/Denton/Allen as "add when corpus
    documents are ingested," so creating a project in a not-yet-supported city is
    legitimate. Phase 3 turns an unknown value into a user-facing signal instead
    of a silent DB write.
    """
```
Call it from `api/routes/projects.py` (only where a client-supplied, not
auto-resolved, `municipality` is trusted directly) and `api/routes/query.py`'s
ad hoc `municipality` param. Auto-resolved values from `resolve_jurisdiction` don't
need it — already canonical by construction.

**`rag/agents/prompt_router.py`**: add `"fortworth": "fort_worth"` to
`_JURISDICTION_ALIASES` (the actual bug fix — one line, once Phase 1's
canonicalizer confirms `fortworth` is the standing spelling).

**`db/client.py`**: new `get_jurisdiction_chain(jurisdiction_id: str) -> list[str]`
near the existing `get_jurisdiction`, one round trip:
```sql
WITH RECURSIVE chain AS (
    SELECT id, parent_id, 1 AS depth FROM jurisdictions WHERE id = %(start)s
    UNION ALL
    SELECT j.id, j.parent_id, chain.depth + 1
    FROM jurisdictions j JOIN chain ON j.id = chain.parent_id
    WHERE chain.depth < 10
)
SELECT id FROM chain ORDER BY depth;
```
e.g. `dallas` → `["dallas", "dallas-county", "texas", "federal"]`. No caching
needed (~15 rows total).

**Migration `037_match_chunks_jurisdiction_hierarchy.sql`** — re-verify 037 is
still free with `ls db/migrations/ | sort -V | tail -5` before creating the file.
Follow the repo's own established `DROP`-then-`CREATE OR REPLACE` pattern
(migration `005`) — **do not** add a 4th parameter; change the 3rd parameter's
*type* instead, to avoid the exact overload-ambiguity bug
`scripts/fix_match_chunks_overload.py` already had to clean up once:
```sql
DROP FUNCTION IF EXISTS match_chunks(vector, integer, text);

CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding      vector(768),
    match_count          int DEFAULT 5,
    filter_municipality  text[] DEFAULT NULL   -- was `text`; now a jurisdiction chain
)
RETURNS TABLE (...unchanged columns...)
LANGUAGE sql STABLE AS $$
    SELECT ...
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.document_status = 'active' AND d.is_current = true AND c.status = 'active'
      AND (filter_municipality IS NULL OR d.municipality = ANY(filter_municipality))
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
$$;
```
⚠️ **Per `AGENTS.md`'s RAG Quality Rules ("never change retrieval without running
RAGAs immediately after") and migration 031's own comment marking `match_chunks` as
retrieval-critical: run RAGAs immediately after applying this migration, before
doing anything else.**

Python call sites to update:
- `db/client.py` (~L603-654) — rename the `match_chunks` wrapper's `municipality: str | None` param to `municipalities: list[str] | None`, pass straight through (psycopg adapts a Python list to a Postgres array).
- `rag/retriever.py` (`retrieve()`, ~L297) — compute the chain immediately before the call: `chain = get_jurisdiction_chain(municipality) if municipality else None`. Leave `retrieve()`'s own `municipality: str | None` parameter untouched — `_apply_non_municipal_authority_guardrails` (~L90-125) keys off that single original string and only fires when `municipality is None`, which Phase 1 doesn't change.
- Same-phase, same-PR: `search_chunks_bm25`/`_search_chunks_with_tsquery` (`db/client.py` ~L837-911) do their own raw-SQL municipality equality filter — apply the same `= ANY(...)` change so there's no latent trap once `RETRIEVAL_HYBRID_ENABLED` is eventually flipped on.

**Optional, still not created — migration `039_jurisdiction_fk_constraints.sql`**
(038 is now taken by Phase 4's `overlays` table — re-check `ls db/migrations/` for
the actual next-free number before creating this), gated:
```sql
ALTER TABLE documents ADD CONSTRAINT fk_documents_municipality_jurisdiction FOREIGN KEY (municipality) REFERENCES jurisdictions(id);
ALTER TABLE projects  ADD CONSTRAINT fk_projects_municipality_jurisdiction  FOREIGN KEY (municipality) REFERENCES jurisdictions(id);
```
Only apply if the orphan check below returns zero rows (existing corpus-row
cleanliness can't be verified from a machine without the corpus).

### Verify (on the corpus machine)

```bash
py scripts/check_migrations.py --local   # confirm current state before starting
# Orphan check — must return zero rows before applying the optional 039 FK migration:
#   SELECT DISTINCT municipality FROM documents WHERE municipality NOT IN (SELECT id FROM jurisdictions);
#   SELECT DISTINCT municipality FROM projects  WHERE municipality NOT IN (SELECT id FROM jurisdictions) AND municipality IS NOT NULL;
py scripts/apply_migration.py db/migrations/037_match_chunks_jurisdiction_hierarchy.sql
py -m evaluation.ragas_eval   # MANDATORY — record faithfulness/relevancy/context-precision before vs. after; a drop is stop-ship
py -m pytest tests/test_retriever.py tests/test_jurisdiction_ids.py -v
```

---

## Phase 2 — Real municipal boundary polygons

### The problem this fixes

`municipal_boundaries` has one row — a hand-drawn rectangle for Dallas, explicitly
commented "not production-grade city limits" in `db/seeds/municipal_boundaries.sql`,
spanning roughly lat 32.55–33.02, lng -97.10 to -96.45 (large enough to
geographically swallow parts of neighboring cities). `docs/backlog.md` already
lists real, free open-data GIS sources for every DFW city; nobody has loaded them,
and the loader script it names doesn't exist yet.

### Implementation

New `scripts/load_gis_boundaries.py`, following the same `_db_target.py` pattern
already used by `scripts/fix_match_chunks_overload.py`/`scripts/check_migrations.py`
(`_db_target.resolve(...)`, `_db_target.banner(target, read_only=False)`,
`_db_target.ensure_reachable(target)`), matching the filename `docs/backlog.md`
already expects ("extended, not replaced" per city).

Deliberately no new heavy geo dependency (no GDAL/fiona/geopandas/pyproj — risky to
assume installable on a machine that can't be inspected in advance). `shapely>=2.0`
and `requests` are already project dependencies and are sufficient:
- `--geojson <path-or-url>`: a plain GeoJSON Feature/FeatureCollection (most city
  open-data portals export this directly), fetched via `requests` if it's a URL.
- `--arcgis-query <feature-service-base-url>`: appends
  `?where=1=1&outFields=*&f=geojson&outSR=4326` and fetches — covers Dallas's own
  named source (an ArcGIS `MapServer`) with no reprojection code needed (both modes
  return WGS84 GeoJSON directly).
- Positional `jurisdiction_id`, required. The script calls `get_jurisdiction()`
  first and errors clearly (pointing at `db/seeds/jurisdictions.sql`) if that row
  doesn't exist — never silently insert an orphaned boundary.
- Parses features, `shapely.ops.unary_union`s them, coerces to `MultiPolygon`,
  `INSERT ... ON CONFLICT (jurisdiction_id) DO UPDATE` into `municipal_boundaries`
  — the same upsert shape the pilot seed already uses, so re-running this for
  `dallas` is exactly how the pilot envelope gets replaced with a real polygon.
- `--dry-run` (parse/validate/print feature count + centroid, no write).
- `--validate-address "<address>"` (runs the real resolver against the just-loaded
  boundary and prints whether it resolves to the expected id) — this directly
  implements `docs/backlog.md`'s own documented step 4.

Coverage for this phase: **Dallas** (replace the pilot envelope — same
`jurisdiction_id`, upsert handles it), **Plano**, **Fort Worth** (the three cities
with real corpus documents), plus Dallas/Tarrant/Collin county boundaries and the
Texas state boundary if a source is readily on hand (all four are already seeded
in `jurisdictions.sql` — only the geometry is missing). Sources named in
`docs/backlog.md`: Dallas — `gis.dallascityhall.com` ArcGIS CityBoundary
MapServer; Plano — `data.plano.gov` city-limits dataset; Fort Worth —
`data.fortworthtexas.gov` city-limits dataset.

**Re-seed hazard**: `scripts/init_rds_db.py` replays every file in `db/seeds/*.sql`
on a full rebuild, including the pilot-envelope `municipal_boundaries.sql`. Once
this phase loads real polygons, **stub that seed file down to a comment pointing
at this loader script** (a real multi-KB polygon has no business being pasted into
a git-tracked seed file) — and note explicitly: *any future full DB rebuild via
`init_rds_db.py` requires re-running this phase's loader commands for every city
before jurisdiction resolution works again.*

### Verify (on the corpus machine)

```bash
py scripts/load_gis_boundaries.py dallas --arcgis-query https://gis.dallascityhall.com/sharedmaps/rest/services/basemap/CityBoundary/MapServer --dry-run
py scripts/load_gis_boundaries.py dallas --arcgis-query https://gis.dallascityhall.com/sharedmaps/rest/services/basemap/CityBoundary/MapServer
py scripts/load_gis_boundaries.py dallas --validate-address "1500 Marilla St, Dallas, TX"   # City Hall — known-good
# repeat for plano, fortworth with their own sources
# sanity check — Dallas's area should look like a real city, not a 50km bounding box:
#   SELECT jurisdiction_id, boundary_name, ST_Area(geom::geography) / 1e6 AS sq_km FROM municipal_boundaries ORDER BY jurisdiction_id;
py -m pytest tests/test_load_gis_boundaries_script.py -v
```

---

## Phase 3 — Deterministic "outside coverage area" warning

### The problem this fixes

Today the only "we might not have this" signal is a generic low-confidence
retrieval abstain message, which isn't a real coverage check and currently
recommends Frisco/McKinney (which have no documents). There's no explicit,
deterministic "this address is outside our supported area" check anywhere.

Recommended user-facing term: **"coverage area"** — reads clearly without sounding
overly legal/rigid.

### Implementation

New `rag/coverage.py` — single source of truth, reused by every call site below:
```python
@dataclass
class CoverageResult:
    status: str          # "covered" | "no_documents" | "no_boundary_data" | "unresolved"
    municipality: str | None
    message: str

def check_coverage(*, municipality: str | None, latitude: float | None, longitude: float | None) -> CoverageResult:
    """
    - municipality set → zero active documents for it → "no_documents"
    - municipality unset, lat/lng set → point-in-polygon miss → "no_boundary_data"
      (message should hedge: could be truly unsupported, or just a city Phase 2
      hasn't loaded yet)
    - neither set → "unresolved" (nothing to check yet, not a warning)
    - otherwise → "covered"
    """

def covered_municipalities() -> list[str]:
    """Cities with >=1 active document — also feeds Phase 5's generator.py fix."""
```

Surface it two ways:
- New `GET /projects/{project_id}/coverage`, mirroring the existing deterministic,
  non-LLM `GET /projects/{project_id}/permit-strategy` route
  (`api/routes/projects.py` ~L180-206) — no model call needed. Frontend: a
  dashboard banner + "petition this area" CTA linking to Phase 4's petition UI.
- A field alongside the existing `resolved_municipality`/`conflict_warnings` in
  `api/schemas.py`'s `AnswerResponse`, computed in the Manager pipeline
  (`rag/agents/manager.py`, alongside `_resolve_municipality`), so it also shows up
  inline on a chat answer, not just a dashboard page.

Fix the misleading fallback: `rag/generator.py`'s hardcoded
`["Dallas", "Plano", "Fort Worth", "Frisco", "McKinney"]` (in the low-confidence
abstain prompt/message) → read from `covered_municipalities()` instead of a
hand-typed literal, so the two can never drift apart again.

### Verify (on the corpus machine)

```bash
py -m pytest tests/test_coverage.py -v
# manual: GET /api/projects/{id}/coverage for a Dallas project → expect "covered"
# manual: same for a Frisco-address project → expect "no_documents"
```

---

## Phase 4 — Project-level historic/conservation/HOA upload + petition system

### The ask this implements (direct quote from the requester)

> "the ability to upload any historic or conservation district documentation at
> the project level, if it is pertinent to something like a neighborhood (like
> Swiss Ave Historic District), then it could be petitioned to be added to the
> corpus with a tight boundary so it doesn't bleed into non-affected property
> queries... this idea could also be adjusted for HOA bylaws."

Note: "Swiss Ave Historic District" isn't a hypothetical — it's the literal name
of the one placeholder polygon already sitting in
`db/gis_data/dallas/historic_districts.geojson`, wired to `rag/gis.py`'s
Dallas-only overlay lookup. This phase turns that one hardcoded pilot into a real,
general system.

### Implementation

New migration `038_overlays.sql` (the optional FK-constraints migration from
Phase 1 was skipped, so 038 was free — see `db/migrations/038_overlays.sql`):
```sql
CREATE TYPE overlay_type AS ENUM ('historic_district', 'conservation_district', 'hoa', 'other');
CREATE TYPE overlay_status AS ENUM ('petitioned', 'approved', 'rejected');

CREATE TABLE overlays (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    text NOT NULL,
    overlay_type            overlay_type NOT NULL,
    jurisdiction_id         text REFERENCES jurisdictions(id),
    geom                    geometry(MultiPolygon, 4326),   -- nullable until finalized
    status                  overlay_status NOT NULL DEFAULT 'petitioned',
    petitioned_by           uuid REFERENCES users(id) ON DELETE SET NULL,
    petitioning_project_id  uuid REFERENCES projects(id) ON DELETE SET NULL,
    approved_by             uuid REFERENCES users(id) ON DELETE SET NULL,
    approved_at             timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_overlays_geom ON overlays USING gist (geom);
CREATE INDEX idx_overlays_status ON overlays (status);
CREATE TRIGGER trg_overlays_updated_at BEFORE UPDATE ON overlays
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();  -- reuses the existing trigger fn

ALTER TABLE documents ADD COLUMN overlay_id uuid REFERENCES overlays(id) ON DELETE SET NULL;
CREATE INDEX idx_documents_overlay ON documents (overlay_id) WHERE overlay_id IS NOT NULL;
```
This generalizes the current Dallas-only, TEXT-column + flat-GeoJSON-file pattern
(`projects.historic_district`/`conservation_district`, `rag/gis.py`) into one
generic, type-agnostic model — extensible to any city/type (including HOA) with no
further schema changes. **Additive, not a replacement** — leave `rag/gis.py` and
the two existing project columns working as-is for Dallas; a later cleanup could
migrate Dallas's two placeholder districts into real `overlays` rows once this ships.

**"Trusted end-user" — reuse existing infrastructure, don't invent a new role.**
`docs/sprint9_users_projects.md` already gates "share document into project"
(`POST /projects/{id}/documents`) at `editor/owner`. Reuse that exact tier: a
project's own editor/owner is "trusted" for that project's petitions. Zero new
role/column needed.

New `api/routes/overlays.py`:
- `POST /projects/{project_id}/overlays` — multipart (file + `name` +
  `overlay_type` + notes), gated `editor/owner`. Reuse the existing chunk/embed
  background-processing helper from `api/routes/upload.py` (extract to a small
  shared function rather than duplicating). Creates an `overlays` row
  (`status='petitioned'`, `geom` defaulted to a small buffer — e.g. `ST_Buffer` ~200m
  — around the project's own lat/lng, since expecting a v1 petitioner to hand-draw
  a precise polygon isn't realistic) and a `documents` row with **both**
  `project_id=<petitioning project>` (visible to that project immediately,
  regardless of approval) **and** `overlay_id=<new overlay>` (dormant until
  approved), `source_tier=3`.
- `PATCH /admin/overlays/{overlay_id}/approve` — staff-gated, sets
  `status='approved'`/`approved_by`/`approved_at`; can optionally replace the
  petitioner's default buffer with a refined "tight boundary" polygon before
  approving.

Retrieval — new `match_overlay_chunks` in `db/client.py`:
```sql
SELECT c.*, d.doc_id, d.municipality, d.source_tier,
       1 - (c.embedding <=> %(qv)s) AS similarity
FROM chunks c
JOIN documents d ON d.id = c.document_id
JOIN overlays o ON o.id = d.overlay_id
WHERE o.status = 'approved'
  AND ST_Contains(o.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326))
  AND d.document_status = 'active' AND c.status = 'active'
ORDER BY c.embedding <=> %(qv)s LIMIT %(top_k)s;
```
Called from `rag/mini_rag.py` whenever the requesting project has lat/lng set,
merged alongside the existing corpus/project-chunk merge — this is precisely the
"surfaces for **any** project inside the tight boundary, not just the one that
uploaded it" requirement.

**Private knowledge-base doc section** (lightweight — prose, not a new subsystem):
add to this file or a short new `docs/overlay_petitions.md` covering: where to find
a source document (city GIS/preservation-commission portals, an HOA's own bylaws
PDF), how to submit a petition via the new UI, and what petitioned → approved
means (an approved overlay's documents become visible to any other project
physically inside its boundary, not just the one that uploaded them).

### Verify (on the corpus machine)

```bash
py scripts/apply_migration.py db/migrations/038_overlays.sql
py -m pytest tests/test_overlays_routes.py tests/test_db_client_overlays.py tests/test_retriever.py -v
# manual: petition from project A (address inside the target neighborhood) →
# admin-approve → confirm project B, a DIFFERENT project whose address also
# falls inside the approved boundary, can now retrieve the approved document.
```

---

## Phase 5 — Copy cleanup

- `AGENTS.md` (identity section) and `README.md` — "Dallas, Plano, Frisco,
  McKinney, and Fort Worth" → "Dallas, Plano, and Fort Worth (Frisco/McKinney
  planned — see docs/backlog.md)".
- `docs/backlog.md` — fix `fort-worth` → `fortworth` in the GIS status table
  (Phase 1's canonical spelling), and flip rows to "✅ Loaded" as Phase 2 actually
  lands them, recording the real source URL used.
- `docs/postgis_migration_checklist.md` is a Sprint-4 planning artifact for work
  that has already shipped (PostGIS is enabled, `municipal_boundaries` already
  exists) — add a one-line "superseded by docs/jurisdiction_and_gis_runbook.md"
  header rather than leaving it looking like an open task.

---

## Standing hazard: confirm the DB target before touching anything

`.env` overrides `.env.local` with `override=True`, and `ENVIRONMENT=production`
does not necessarily mean the real prod RDS — a machine's `.env.production` can
point at an in-VPC hostname that resolves to a different local DB. Before any step
above: run `py scripts/check_migrations.py --local`, then re-run against the
actual intended target once identified, and **read the banner's Target + Source
lines every time** — never assume. Reuse `scripts/_db_target.py`'s shared
`--local`/`--database-url` resolution in any new script here rather than calling
`bootstrap_env()` bare.
