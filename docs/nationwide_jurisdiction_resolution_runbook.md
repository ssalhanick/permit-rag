# Nationwide Jurisdiction Resolution — Deployment Runbook

Branch: `feat/jurisdiction`, commit `638e30f`.

**Run the DB-touching steps on the machine with the real corpus and database.**
This machine's DB is empty, so migrations/seed/RAGAs steps below were written
and unit-tested here (880 tests pass, code compiles clean) but never applied or
run against a live database. Before any step that touches a database, read the
Target + Source lines from `scripts/_db_target.py`'s banner every time — see
`db/client.py`'s `.env` vs `.env.local` note if the target looks wrong.

## What changed

Address resolution now falls back to the Census Bureau's own `geographies`
lookup for any US address instead of requiring a locally-loaded polygon —
see [rag/jurisdiction_resolver.py](../rag/jurisdiction_resolver.py) for the
design rationale in the module docstring. Full detail in the commit message
(`git show 638e30f --stat` / `git log -1 638e30f`).

⚠ This touches retrieval filtering indirectly: `resolve_jurisdiction_for_point`
feeds `get_jurisdiction_chain()`, which widens `match_chunks`/BM25 filtering.
Per this repo's retrieval-change rule, run RAGAs before merging to
`deployment/sites` (Step 6) — do not bundle this with any other retrieval
change.

## Order of operations

### 1. Pull and install

```bash
git checkout feat/jurisdiction
git pull
source .venv/bin/activate   # or the corpus machine's equivalent
pip install -r requirements.txt
```

### 2. Confirm DB target, then run the full test suite

```bash
py scripts/check_migrations.py   # read the Target + Source lines — confirm this is the intended DB
py -m pytest tests/ -q           # expect 880 passed; new migration 046 has a probe, so this also
                                  # tells you whether 046 is already applied on this DB
```

Do not proceed past this point if the banner names a host you didn't expect.

### 3. Apply migration 046 (drops the Dallas pilot polygon)

```bash
py scripts/apply_migration.py db/migrations/046_drop_dallas_pilot_boundary.sql
```

Safe to re-run — it's a `DELETE ... WHERE`, a no-op once the row is gone.
This is a one-way deletion of placeholder data only (the pilot rectangle was
never production boundary data); there's nothing to roll back. If Dallas-
specific override precision is ever needed, load a real polygon via
`scripts/load_gis_boundaries.py` — the table and script still exist, just
narrowed in scope (see the resolver's module docstring).

### 4. Seed states + counties

```bash
py scripts/seed_states_counties.py --dry-run     # review the fetch/parse counts and sample rows first
py scripts/seed_states_counties.py               # then run for real
```

Expect roughly 51 state rows and ~3,140 county rows; territories (AS, GU, MP,
PR, VI) are intentionally skipped. The script fetches Census's plain-text
reference lists live (`www2.census.gov`), so it needs outbound network access
from wherever it runs. It's idempotent (`ON CONFLICT DO NOTHING` via
`db.client.upsert_jurisdiction`) — re-running is safe and only fills gaps.

Verify the three legacy DFW counties didn't get duplicated:

```bash
py -c "from db.client import get_jurisdiction; print(get_jurisdiction('dallas-county'))"
```

Should print the existing hand-seeded row (no `dallas-county-texas` row should
exist alongside it — `jurisdiction_ids.KNOWN_ALIASES` is what prevents that).

### 5. Manual resolution spot-checks

```bash
py -c "
from rag.jurisdiction_resolver import resolve_jurisdiction
for addr in [
    '1500 Marilla St, Dallas, TX 75201',       # regression check: still resolves to 'dallas', not 'dallas-texas'
    '1 Municipal Dr, Fishers, IN 46038',        # genuinely new nationwide city — see the alias note below
    'FM 3078, Loving County, TX',               # unincorporated — should resolve to a *-county id, not fail
]:
    r = resolve_jurisdiction(addr)
    print(addr, '->', r.jurisdiction_id, '|', r.error)
"
```

Confirm the Fishers, IN address resolves to `fishers` (not `fishers-indiana`)
— `documents/catalog.json` was updated in the prior commit (`d6c7400`,
"importing indiana and mckinney/frisco") with `"municipality": "fishers"`
using the corpus's older bare-slug convention, before the nationwide
state-suffixing convention existed. `jurisdiction_ids.KNOWN_ALIASES` maps
`fishers-indiana` back onto `fishers` to match — this was caught and fixed
during this session specifically because that commit landed while this work
was in progress. **Going forward, prefer state-suffixed `municipality` values
for new nationwide catalog entries** (e.g. `"fishers-indiana"`) so new cities
don't need a hand-added alias each time; only add one when an existing bare
slug (like `fishers`, or a future one) must be preserved for compatibility
with already-ingested documents.

### 6. RAGAs gate (mandatory, do not skip)

```bash
py -m evaluation.ragas_eval
```

Compare faithfulness / answer-relevancy / context-precision against the last
recorded baseline. A drop is stop-ship — fix before merging, per this
project's rule of gating each retrieval-affecting change with its own RAGAs
run rather than bundling several. The expected effect here is neutral for
existing DFW queries (`dallas`/`fortworth`/`plano` resolution is unchanged —
same ids, same jurisdiction chain) and only adds new abstain cases for
addresses that previously errored outright and now resolve to a real,
sparsely-covered jurisdiction (the grounding gate's `jurisdiction_mismatch`
path handles those, per `rag/agents/manager.py::_grounding_verdict`).

### 7. Merge and deploy

Once RAGAs passes, open a PR into `deployment/sites` as usual. Don't run
`deploy.ps1` — this repo auto-deploys to AWS on every push to
`deployment/sites` (`.github/workflows/deploy.yml`), so merging is the
deploy. Migration 046 and the state/county seed must already be applied on
production's database *before or immediately after* that merge — the app
code works either way (fallback degrades gracefully if a county/state row is
momentarily missing), but resolution won't widen to state/federal content
for new cities until the seed has run there too.

## Rollback

- **App code**: revert the merge commit, redeploy via the same GHA path.
- **Migration 046**: no automated rollback (deleted placeholder data, not
  something to restore). If needed, re-add a Dallas polygon via
  `scripts/load_gis_boundaries.py`.
- **State/county seed**: additive only: harmless to leave in place even if
  the app code is rolled back — `get_jurisdiction_chain` and `check_coverage`
  behave the same with or without the wider seed present.

## Known follow-ups (not blocking this deploy)

- `scripts/seed_states_counties.py` has no `--states-only`/`--counties-only`
  split and no retry-on-partial-failure handling — fine for a one-time run,
  worth revisiting if it ever needs to be re-run incrementally at scale.
- The geographies cache is in-process only (not shared across API workers or
  persisted across restarts) — revisit as a DB-backed cache if Census lookup
  volume ever makes that worthwhile (see the cache comment in
  `rag/jurisdiction_resolver.py`).
- Any *future* nationwide catalog entry with a bare (non-state-suffixed)
  `municipality` value will silently fail to resolve until someone adds a
  `KNOWN_ALIASES` entry, exactly like the Fishers case in Step 5. Worth a
  lightweight catalog-lint check if nationwide ingestion becomes routine.
