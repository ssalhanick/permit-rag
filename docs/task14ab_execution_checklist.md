# Task 14A/B Execution Checklist

Scope:
- Task 14A: add PostGIS in Docker dev stack safely
- Task 14B: load first municipal boundary layer safely
- No production changes in this checklist

## 0) Preconditions

- [ ] Working tree clean or changes backed up
- [ ] Docker Desktop running
- [ ] Current DB backup created
- [ ] `docs/postgis_migration_checklist.md` gate approved

Backup command:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db pg_dump -U postgres -d permit_rag > backup_pre_task14ab.sql`

## 1) Task 14A — PostGIS enable in local Docker

### 1.1 Change set

- [ ] Update `docker-compose.yml` image to PostGIS-capable image
- [ ] Add extension init SQL for PostGIS (dev only)
- [ ] Keep pgvector path working

### 1.2 Apply

- [ ] Stop stack
- [ ] Recreate DB container with new image
- [ ] Start stack and wait for healthy status

Commands:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker compose down`

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker compose up -d`

### 1.3 Validate extensions

- [ ] `postgis` extension exists
- [ ] `vector` extension exists

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

- [ ] Load one city boundary layer only (pilot)
- [ ] Store as SRID 4326 multipolygon
- [ ] Link to jurisdiction ID

### 2.2 Data checks

- [ ] Source file has expected geometry type
- [ ] CRS transformed to EPSG:4326 before insert
- [ ] Row count > 0 after load

### 2.3 Validate geometry

- [ ] Geometry valid check passes
- [ ] Spatial index exists
- [ ] Sample point-in-polygon query works

Validation command template:

`cd "c:\Users\ssalh\Grad School\2026\02_Summer\MIS6V99\permit_rag"; docker exec permit_rag_db psql -U postgres -d permit_rag -c "SELECT COUNT(*) FROM municipal_boundaries;"`

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

- [ ] PostGIS + pgvector both present
- [ ] API retrieval path still passes smoke checks
- [ ] one boundary layer loaded and queryable
- [ ] rollback tested or rollback commands validated
- [ ] `STATE.md` and journal updated with outcomes
