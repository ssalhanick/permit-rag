-- db/seeds/municipal_boundaries.sql — Seed municipal boundaries
-- Dallas pilot boundary (coarse envelope) for Task 14B validation.
-- This is a pilot geometry for spatial plumbing checks, not production-grade city limits.

INSERT INTO municipal_boundaries (
    jurisdiction_id,
    boundary_name,
    source_name,
    source_url,
    geom
)
VALUES (
    'dallas',
    'City of Dallas (pilot envelope)',
    'internal-task14b-pilot',
    NULL,
    ST_Multi(
        ST_GeomFromText(
            'POLYGON((
                -97.10 32.55,
                -97.10 33.02,
                -96.45 33.02,
                -96.45 32.55,
                -97.10 32.55
            ))',
            4326
        )
    )
)
ON CONFLICT (jurisdiction_id) DO UPDATE SET
    boundary_name = EXCLUDED.boundary_name,
    source_name = EXCLUDED.source_name,
    source_url = EXCLUDED.source_url,
    geom = EXCLUDED.geom,
    loaded_at = NOW();
