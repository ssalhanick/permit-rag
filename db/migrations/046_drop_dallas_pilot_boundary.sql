-- 046_drop_dallas_pilot_boundary.sql
-- Retract the coarse, hand-drawn Dallas "pilot envelope" placeholder from
-- municipal_boundaries. It was never production-grade city limits, and
-- nationwide jurisdiction resolution (rag/jurisdiction_resolver.py ::
-- resolve_jurisdiction_for_point) now falls back to the Census Bureau's own
-- `geographies` lookup rather than requiring a locally-loaded polygon — a
-- stale pilot rectangle left in place would silently shadow that fallback
-- for every Dallas address instead of letting the real resolution path run.
--
-- Seeds are additive upserts (db/seeds/municipal_boundaries.sql), so
-- removing the INSERT there doesn't retract a row already applied to a
-- given database — this migration is the actual retraction.
--
-- Safe to re-run: DELETE ... WHERE is a no-op once the row is gone.

DELETE FROM municipal_boundaries
WHERE jurisdiction_id = 'dallas'
  AND source_name = 'internal-task14b-pilot';
