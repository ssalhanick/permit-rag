-- db/seeds/jurisdictions.sql — Seed jurisdictions from actual DB corpus
-- Generated from: SELECT DISTINCT municipality, authority_level FROM documents (2026-06-03)
-- Corpus municipalities: dallas, fortworth, plano, texas, federal
-- County rows added as GIS stubs (no dept_url yet).
--
-- Run: Get-Content db/seeds/jurisdictions.sql | docker exec -i permit_rag_db psql -U postgres -d permit_rag
--
-- Add new city rows here as new documents are ingested for that jurisdiction.
-- Do NOT add a city row until documents exist for it in the DB.

-- ── Tier 0: Federal ──────────────────────────────────────────
INSERT INTO jurisdictions (id, name, level, parent_id, dept_name, dept_url)
VALUES (
    'federal',
    'United States Federal Government',
    'federal',
    NULL,
    NULL,
    NULL
)
ON CONFLICT (id) DO UPDATE SET
    name      = EXCLUDED.name,
    level     = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id;

-- ── Tier 1: State ────────────────────────────────────────────
INSERT INTO jurisdictions (id, name, level, parent_id, dept_name, dept_url)
VALUES (
    'texas',
    'State of Texas',
    'state',
    'federal',
    'Texas Department of Licensing and Regulation',
    'https://www.tdlr.texas.gov/'
)
ON CONFLICT (id) DO UPDATE SET
    name      = EXCLUDED.name,
    level     = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    dept_name = EXCLUDED.dept_name,
    dept_url  = EXCLUDED.dept_url;

-- ── Tier 2: Counties (GIS stubs — no dept_url) ───────────────
INSERT INTO jurisdictions (id, name, level, parent_id, dept_name, dept_url)
VALUES
    ('dallas-county',  'Dallas County',  'county', 'texas', NULL, NULL),
    ('tarrant-county', 'Tarrant County', 'county', 'texas', NULL, NULL),
    ('collin-county',  'Collin County',  'county', 'texas', NULL, NULL)
ON CONFLICT (id) DO UPDATE SET
    name      = EXCLUDED.name,
    level     = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id;

-- ── Tier 3: Cities (corpus municipalities only) ───────────────
-- dallas — 5 docs in corpus
INSERT INTO jurisdictions (id, name, level, parent_id, dept_name, dept_url)
VALUES (
    'dallas',
    'City of Dallas',
    'city',
    'dallas-county',
    'Dallas Development Services Department',
    'https://dallascityhall.com/departments/sustainabledevelopment/Pages/default.aspx'
)
ON CONFLICT (id) DO UPDATE SET
    name      = EXCLUDED.name,
    level     = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    dept_name = EXCLUDED.dept_name,
    dept_url  = EXCLUDED.dept_url;

-- fortworth — 2 docs in corpus (stored as 'fortworth', no hyphen)
INSERT INTO jurisdictions (id, name, level, parent_id, dept_name, dept_url)
VALUES (
    'fortworth',
    'City of Fort Worth',
    'city',
    'tarrant-county',
    'Fort Worth Development Services',
    'https://www.fortworthtexas.gov/departments/development-services'
)
ON CONFLICT (id) DO UPDATE SET
    name      = EXCLUDED.name,
    level     = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    dept_name = EXCLUDED.dept_name,
    dept_url  = EXCLUDED.dept_url;

-- plano — 6 docs in corpus
INSERT INTO jurisdictions (id, name, level, parent_id, dept_name, dept_url)
VALUES (
    'plano',
    'City of Plano',
    'city',
    'collin-county',
    'Plano Building Inspections',
    'https://www.plano.gov/266/Building-Inspections'
)
ON CONFLICT (id) DO UPDATE SET
    name      = EXCLUDED.name,
    level     = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    dept_name = EXCLUDED.dept_name,
    dept_url  = EXCLUDED.dept_url;

-- Future cities (add when corpus documents are ingested for that jurisdiction):
-- arlington → tarrant-county
-- frisco    → collin-county
-- mckinney  → collin-county
-- irving    → dallas-county
-- garland   → dallas-county
-- denton    → denton-county (add denton-county row first)
-- allen     → collin-county
