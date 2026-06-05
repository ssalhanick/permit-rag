# Task 14A/B Execution Checklist

Scope:
- Task 14A: add PostGIS in Docker dev stack safely
- Task 14B: load first municipal boundary layer safely
- No production changes in this checklist

## 0) Preconditions

- [x ] Working tree clean or changes backed up
- [ x] Docker Desktop running
- [x ] Current DB backup created
- [ ] `docs/postgis_migration_checklist.md` gate approved

Backup command:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db pg_dump -U postgres -d permit_rag > backup_pre_task14ab.sql`

## 1) Task 14A — PostGIS enable in local Docker

### 1.1 Change set

- [x] Update `docker-compose.yml` image to PostGIS-capable image
- [x] Add extension init SQL for PostGIS (dev only)
- [x] Keep pgvector path working

### 1.2 Apply

- [x] Stop stack
- [x] Recreate DB container with new image
- [x] Start stack and wait for healthy status

Commands:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker compose down`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker compose up -d`

### 1.3 Validate extensions

- [x] `postgis` extension exists
- [x] `vector` extension exists

Commands:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT extname FROM pg_extension WHERE extname IN ('postgis','vector') ORDER BY extname;"`

### 1.4 App regression smoke

- [ ] API starts
- [ ] `/health` returns healthy
- [ ] one retrieval query succeeds

Commands:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; py -m uvicorn api.main:app --reload --port 8000`

`curl -s "http://localhost:8000/health"`

## 2) Task 14B — Load first boundary layer

### 2.1 Minimal target

- [x] Load one city boundary layer only (pilot)
- [x] Store as SRID 4326 multipolygon
- [x] Link to jurisdiction ID

### 2.2 Data checks

- [x] Source file has expected geometry type
- [x] CRS transformed to EPSG:4326 before insert
- [x] Row count > 0 after load

### 2.3 Validate geometry

- [x] Geometry valid check passes
- [x] Spatial index exists
- [x] Sample point-in-polygon query works

Validation command template:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT COUNT(*) FROM municipal_boundaries;"`

Task 14B pilot load commands:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; Get-Content db/migrations/006_jurisdictions.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; Get-Content db/seeds/jurisdictions.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; Get-Content db/migrations/007_postgis_extension.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; Get-Content db/migrations/008_municipal_boundaries_pilot.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag`

Task 14B geometry + point-in-polygon checks:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT jurisdiction_id, ST_SRID(geom) AS srid, GeometryType(geom) AS geom_type, ST_IsValid(geom) AS is_valid FROM municipal_boundaries;"`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT indexname, indexdef FROM pg_indexes WHERE tablename='municipal_boundaries' ORDER BY indexname;"`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT jurisdiction_id FROM municipal_boundaries WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(-96.7970, 32.7767), 4326));"`

## 3) Rollback Plan

Trigger rollback if:
- API cannot start after extension/image change
- retrieval queries fail due to extension/schema issues
- boundary load corrupts expected geometry constraints

Rollback commands:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker compose down`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker compose up -d`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec -i permit_rag_db psql -U postgres -d permit_rag < backup_pre_task14ab.sql`

## 4) Exit Criteria

- [x] PostGIS + pgvector both present
- [ ] API retrieval path still passes smoke checks
- [x] one boundary layer loaded and queryable
- [x] rollback tested or rollback commands validated
- [x] `STATE.md` and journal updated with outcomes
