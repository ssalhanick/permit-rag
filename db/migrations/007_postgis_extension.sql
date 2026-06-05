-- Migration 007: Enable PostGIS on existing databases
-- Run:
--   Get-Content db/migrations/007_postgis_extension.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag

CREATE EXTENSION IF NOT EXISTS postgis;
