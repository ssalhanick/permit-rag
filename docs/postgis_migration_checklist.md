# PostGIS Migration Checklist (Planning Only)

Purpose:
- Prepare safe path to GIS features
- Do not execute risky DB change in this step

Status:
- Sprint 4 planning artifact
- No migration file created yet
- No extension command executed yet

## 1) Scope and Non-Goals

In scope:
- Define migration checklist
- Define validation and rollback steps
- Define go/no-go gates

Out of scope (for now):
- Running `CREATE EXTENSION postgis`
- Switching production DB image
- Adding geometry/geography columns
- Backfilling spatial data

## 2) Preflight Checklist

- [ ] Confirm target environments (dev/stage/prod) and owners
- [ ] Confirm current DB image and version in each environment
- [ ] Confirm `pgvector` compatibility with intended PostGIS image/version
- [ ] Confirm backup/restore command path is tested for target environment
- [ ] Confirm maintenance window and rollback window are approved
- [ ] Confirm no active migration lock or in-flight deploy

## 3) Compatibility Checklist

- [ ] Validate base image candidates:
  - Option A: `postgis/postgis:<postgres-version>`
  - Option B: managed Postgres with PostGIS pre-enabled
- [ ] Validate required extensions together:
  - `vector`
  - `postgis`
- [ ] Validate client driver behavior (pooling, SSL, timeouts) unchanged
- [ ] Validate migration runner permissions for extension enable

## 4) Dry-Run Plan (Dev First)

- [ ] Snapshot DB backup before any change
- [ ] Bring up clone environment with proposed image/version
- [ ] Run extension enable in clone only:
  - `CREATE EXTENSION IF NOT EXISTS postgis;`
- [ ] Run smoke checks:
  - app startup
  - retrieval query path
  - ingest + embed path
- [ ] Run current test suite subset for DB-touching paths
- [ ] Record timings and any query plan changes

## 5) Rollback Plan

- [ ] Keep pre-change backup artifact and restore instructions
- [ ] Define restore owner and expected restore SLA
- [ ] Define rollback trigger conditions:
  - startup failure
  - retrieval latency regression above threshold
  - extension conflict/error not resolved quickly
- [ ] Document rollback command sequence before go-live

## 6) Validation Gates (Go/No-Go)

Gate A (Before any DB change):
- [ ] Checklist sections 2-5 complete
- [ ] Team sign-off captured

Gate B (After dev dry-run):
- [ ] No functional regressions in API query/upload paths
- [ ] No test regressions in selected test set
- [ ] No unacceptable latency increase

Gate C (Before stage/prod):
- [ ] Backups verified restorable
- [ ] Rollback owner on call
- [ ] Deployment communication sent

## 7) Future Migration Tasks (Not Executed Yet)

- [ ] Add migration file to enable PostGIS in controlled env
- [ ] Add optional geometry columns/tables for municipal boundaries
- [ ] Add spatial indexes (GiST/SP-GiST) where needed
- [ ] Add GIS helper functions in `db/client.py` only (no inline DB calls)
- [ ] Add tests for spatial query behavior

## 8) Test Command Placeholders

Run when DB dry-run starts:

`py -m pytest tests/test_documents_routes.py -v`

`py -m pytest tests/test_governance.py tests/test_permit_classifier.py -v`

`py -m pytest tests/test_api_main.py -v`
