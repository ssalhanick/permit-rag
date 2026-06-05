-- permit_rag schema — Week 1 Foundation
-- Target: Supabase (Postgres 15 + pgvector)
-- Run via Supabase SQL Editor or psql against SUPABASE_DB_URL

-- ─────────────────────────────────────────────────────────
-- 0. Extensions
-- ─────────────────────────────────────────────────────────
create extension if not exists vector;      -- pgvector
create extension if not exists pgcrypto;    -- gen_random_uuid()
create extension if not exists postgis;     -- GIS geometry + spatial functions

-- ─────────────────────────────────────────────────────────
-- 1. Enum types
-- ─────────────────────────────────────────────────────────
create type authority_level as enum (
    'municipal',
    'county',
    'state',
    'federal'
);

create type document_status as enum (
    'active',
    'superseded',
    'repealed',
    'needs_ocr',
    'draft'
);

create type doc_type as enum (
    'building_code',
    'zoning_ordinance',
    'permit_checklist',
    'fire_code',
    'plumbing_code',
    'electrical_code',
    'mechanical_code',
    'energy_code',
    'accessibility_code',
    'osha_standard',
    'administrative_rule',
    'amendment',
    'state_statute',
    'federal_regulation',
    'other'
);

create type verification_stage as enum (
    'download',
    'extraction',
    'chunking',
    'embedding'
);

create type verification_result as enum (
    'pass',
    'fail',
    'skip',
    'needs_ocr'
);

-- ─────────────────────────────────────────────────────────
-- 2. Jurisdictions
-- ─────────────────────────────────────────────────────────
create table jurisdictions (
    id          text primary key,
    name        text not null,
    level       text not null check (level in ('federal', 'state', 'county', 'city', 'district')),
    parent_id   text references jurisdictions(id),
    dept_name   text,
    dept_url    text,
    created_at  timestamptz default now()
);

create index idx_jurisdictions_level on jurisdictions (level);
create index idx_jurisdictions_parent on jurisdictions (parent_id);

-- ─────────────────────────────────────────────────────────
-- 3. Documents — master registry (mirrors registry.json)
-- ─────────────────────────────────────────────────────────
create table documents (
    id              uuid primary key default gen_random_uuid(),
    doc_id          text unique not null,            -- e.g. "dallas-amlegal-code"
    source_url      text not null,
    municipality    text not null,                   -- e.g. "dallas", "plano"
    authority_level authority_level not null,
    doc_type        doc_type not null,
    subject_tags    text[] not null default '{}',
    effective_date  date,
    document_status document_status not null default 'active',
    is_current      boolean not null default true,
    retrieval_weight numeric(3,2) not null default 1.00,
    review_due      date,
    checksum_sha256 text,
    source_etag     text,
    local_path      text,                            -- relative to documents/raw/
    -- Sprint 1 addition
    source_tier     integer not null default 1
                        constraint chk_source_tier check (source_tier in (1, 2, 3)),
    ingested_at     timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    -- Supersession tracking
    superseded_by   uuid references documents(id),

    constraint valid_retrieval_weight
        check (retrieval_weight >= 0.0 and retrieval_weight <= 1.0)
);

create index idx_documents_municipality on documents (municipality);
create index idx_documents_status on documents (document_status);
create index idx_documents_doc_id on documents (doc_id);
create index idx_documents_source_tier on documents (source_tier); -- Sprint 1: tier-based ordering

-- ─────────────────────────────────────────────────────────
-- 4. Chunks — text segments with embeddings
-- ─────────────────────────────────────────────────────────
create table chunks (
    id              uuid primary key default gen_random_uuid(),
    document_id     uuid not null references documents(id) on delete cascade,
    chunk_index     integer not null,                -- position within document
    content         text not null,
    char_count      integer not null,
    page_start      integer,                         -- source PDF page (nullable)
    page_end        integer,
    embedding       vector(768),                     -- nomic-embed-text-v1.5 = 768 dims
    search_vector   tsvector generated always as      -- BM25 hybrid search (Week 4-5 ablation)
                    (to_tsvector('english', content)) stored,
    -- Sprint 1 additions
    content_hash    text,                            -- SHA-256 of content; change detection
    status          document_status not null default 'active', -- chunk-level lifecycle
    created_at      timestamptz not null default now(),

    constraint unique_chunk_per_doc unique (document_id, chunk_index)
);

-- HNSW index for vector similarity search (dense)
create index idx_chunks_embedding on chunks
    using hnsw (embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- GIN index for BM25/full-text search (sparse)
create index idx_chunks_search on chunks using gin (search_vector);

create index idx_chunks_document_id on chunks (document_id);
create index idx_chunks_status on chunks (status);          -- Sprint 1: chunk-level status filter
create index idx_chunks_content_hash on chunks (content_hash); -- Sprint 1: change detection

-- ─────────────────────────────────────────────────────────
-- 5. Ingestion verification log
-- ─────────────────────────────────────────────────────────
create table ingestion_verifications (
    id              uuid primary key default gen_random_uuid(),
    document_id     uuid not null references documents(id) on delete cascade,
    stage           verification_stage not null,
    result          verification_result not null,
    detail          jsonb not null default '{}',      -- stage-specific metrics
    -- Example detail for 'chunking' stage:
    -- {"source_chars": 45000, "chunk_chars": 42300, "coverage_ratio": 0.94}
    verified_at     timestamptz not null default now()
);

create index idx_verifications_document on ingestion_verifications (document_id);
create index idx_verifications_stage on ingestion_verifications (stage);

-- ─────────────────────────────────────────────────────────
-- 6. Query audit log
-- ─────────────────────────────────────────────────────────
create table query_log (
    id              uuid primary key default gen_random_uuid(),
    query_text      text not null,
    municipality    text,                            -- filter used, if any
    top_k           integer not null default 5,
    chunk_ids       uuid[] not null default '{}',    -- chunks retrieved
    answer_text     text,
    citations       jsonb not null default '[]',     -- [{doc_id, chunk_index, score}]
    model           text not null,                   -- LLM model used
    latency_ms      integer,
    created_at      timestamptz not null default now()
);

create index idx_query_log_created on query_log (created_at desc);

-- ─────────────────────────────────────────────────────────
-- 7. Municipal boundaries (Task 14B pilot)
-- ─────────────────────────────────────────────────────────
create table municipal_boundaries (
    id              uuid primary key default gen_random_uuid(),
    jurisdiction_id text not null references jurisdictions(id),
    boundary_name   text not null,
    source_name     text not null,
    source_url      text,
    geom            geometry(MultiPolygon, 4326) not null,
    loaded_at       timestamptz not null default now(),
    constraint uq_municipal_boundaries_jurisdiction unique (jurisdiction_id)
);

create index idx_municipal_boundaries_jurisdiction
    on municipal_boundaries (jurisdiction_id);
create index idx_municipal_boundaries_geom
    on municipal_boundaries using gist (geom);

-- ─────────────────────────────────────────────────────────
-- 8. Purge audit log
-- ─────────────────────────────────────────────────────────
create table purge_audit_log (
    id                  uuid primary key default gen_random_uuid(),
    doc_id              text not null,
    document_id         uuid,
    actor_identity      text not null,
    actor_role          text not null,
    source_tier         integer not null check (source_tier in (1, 2, 3)),
    deleted_chunk_count integer not null default 0,
    local_file_deleted  boolean not null default false,
    created_at          timestamptz not null default now()
);

create index idx_purge_audit_log_doc_id on purge_audit_log (doc_id);
create index idx_purge_audit_log_created on purge_audit_log (created_at desc);

-- ─────────────────────────────────────────────────────────
-- 9. Row-Level Security (RLS)
-- ─────────────────────────────────────────────────────────
-- Enable RLS on all tables. Policies will be added when
-- auth is implemented. For now, service_role key bypasses RLS.

alter table documents enable row level security;
alter table chunks enable row level security;
alter table ingestion_verifications enable row level security;
alter table query_log enable row level security;
alter table municipal_boundaries enable row level security;
alter table purge_audit_log enable row level security;

-- Allow service_role full access (used by backend)
create policy "service_role_all" on documents
    for all using (true) with check (true);
create policy "service_role_all" on chunks
    for all using (true) with check (true);
create policy "service_role_all" on ingestion_verifications
    for all using (true) with check (true);
create policy "service_role_all" on query_log
    for all using (true) with check (true);
create policy "service_role_all" on municipal_boundaries
    for all using (true) with check (true);
create policy "service_role_all" on purge_audit_log
    for all using (true) with check (true);

-- ─────────────────────────────────────────────────────────
-- 10. Auto-update updated_at trigger
-- ─────────────────────────────────────────────────────────
create or replace function update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger trg_documents_updated_at
    before update on documents
    for each row execute function update_updated_at();

-- ─────────────────────────────────────────────────────────
-- 11. Helper: vector similarity search
-- ─────────────────────────────────────────────────────────
create or replace function match_chunks(
    query_embedding  vector(768),
    match_count      int default 5,
    filter_municipality text default null
)
returns table (
    id              uuid,
    document_id     uuid,
    doc_id          text,
    content         text,
    chunk_index     integer,
    municipality    text,
    authority_level authority_level,
    doc_type        doc_type,
    document_status document_status,
    chunk_status    document_status,  -- Sprint 1: chunk-level status
    source_tier     integer,          -- Sprint 1: corpus tier
    ingested_at     timestamptz,      -- Sprint 1: for provenance age calc
    retrieval_weight numeric,         -- Sprint 1: document-level weight
    similarity      float
)
language sql stable
as $$
    select
        c.id,
        c.document_id,
        d.doc_id,
        c.content,
        c.chunk_index,
        d.municipality,
        d.authority_level,
        d.doc_type,
        d.document_status,
        c.status          as chunk_status,
        d.source_tier,
        d.ingested_at,
        d.retrieval_weight,
        1 - (c.embedding <=> query_embedding) as similarity
    from chunks c
    join documents d on d.id = c.document_id
    where d.document_status = 'active'
      and d.is_current = true
      and c.status = 'active'          -- Sprint 1: exclude superseded chunks
      and (filter_municipality is null or d.municipality = filter_municipality)
    order by
        d.source_tier asc,             -- Sprint 1: corpus (Tier 1) first
        c.embedding <=> query_embedding
    limit match_count;
$$;
