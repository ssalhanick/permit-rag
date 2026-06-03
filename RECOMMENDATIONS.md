# permit_rag — Architecture Recommendations

> **Context:** These recommendations were developed during initial product scoping for a RAG-powered construction permit compliance tool targeting the DFW metro market, with planned scalability to multi-jurisdiction deployments. They address core architectural risks identified before MVP development.

---

## Table of Contents

1. [Jurisdiction Resolution — Coordinate-Based Zone Layering](#1-jurisdiction-resolution--coordinate-based-zone-layering)
2. [Ordinance Data Freshness — Graph-Augmented RAG with Provenance Weighting](#2-ordinance-data-freshness--graph-augmented-rag-with-provenance-weighting)
3. [Authority Having Jurisdiction (AHJ) Disclaimer](#3-authority-having-jurisdiction-ahj-disclaimer)
4. [Multi-Permit Compound Project Detection](#4-multi-permit-compound-project-detection)
5. [Document Hierarchy — Corpus Authority vs. User-Uploaded Documents](#5-document-hierarchy--corpus-authority-vs-user-uploaded-documents)

---

## 1. Jurisdiction Resolution — Coordinate-Based Zone Layering

### Problem

Zip codes do not map 1:1 to municipalities. A single zip code can straddle two incorporated cities, a city and an unincorporated county area, or include special overlay districts (historic, conservation, flood) that each carry independent code authority. Using zip code as the primary jurisdiction key will produce incorrect retrieval for edge-case parcels and will not scale to multi-jurisdiction deployments.

### Recommended Approach

Use a **two-pass geocoding + GIS intersection strategy** to resolve the full jurisdiction stack for a given project address before any retrieval occurs.

**Pass 1 — Primary Jurisdiction:**
Geocode the project address to lat/long, then run a point-in-polygon check against municipal boundary GIS layers to determine the governing city or county. Most DFW municipalities publish their boundary shapefiles via open GIS portals.

**Pass 2 — Overlay Districts:**
For the resolved lat/long, check against overlay district polygons in priority order:
- Historic district (city- or state-designated)
- Conservation district
- FEMA Special Flood Hazard Area (SFHA)
- Planned Development (PD) zoning overlays
- HOA-governed areas (where enforceable)

The result is an **ordered jurisdiction stack** — a list of governing authorities from most specific (parcel overlay) to broadest (federal). Retrieval queries are executed against this full stack, with results tagged by their layer of origin.

### Implementation Notes

```python
# Conceptual jurisdiction resolution
def resolve_jurisdiction_stack(address: str) -> list[Jurisdiction]:
    lat, lng = geocode(address)

    primary = point_in_polygon(lat, lng, source="municipal_boundaries")
    overlays = [
        point_in_polygon(lat, lng, source="historic_districts"),
        point_in_polygon(lat, lng, source="conservation_districts"),
        point_in_polygon(lat, lng, source="fema_sfha"),
        point_in_polygon(lat, lng, source="pd_overlays"),
    ]

    # Return ordered stack: overlays first (most specific), primary last
    return [o for o in overlays if o is not None] + [primary]
```

GIS data sources for DFW MVP:
- City boundaries: each city's open data portal (Dallas, Fort Worth, Plano, etc.)
- Historic districts: Texas Historical Commission + city preservation offices
- Flood zones: FEMA National Flood Hazard Layer (NFHL) — accessible via REST API
- PD overlays: city zoning GIS layers (Dallas has a public Zoning Explorer API)

### Scalability Note

Design the `Jurisdiction` entity from day one with a `level` field (`federal | state | county | city | district`) and a `parent_id` foreign key. Zip code can be stored as a lookup convenience but must never be the primary key for jurisdiction resolution.

---

## 2. Ordinance Data Freshness — Graph-Augmented RAG with Provenance Weighting

### Problem

Ordinances are amended continuously. A RAG system that ingests a code document once and never updates it will silently return stale results with no signal to the user that the cited code may have been superseded. In the permit context, this is a high-stakes failure mode — a contractor acting on a superseded setback requirement may have to demolish work.

### Recommended Approach

Build a **provenance graph** alongside the vector store. The graph tracks the legal lineage of every chunk in the corpus, enabling two things: (1) filtering or downweighting superseded content at retrieval time, and (2) surfacing the authority chain behind any result returned to the user.

### Graph Schema

**Node: `RagChunk`** — the primary node; one node per chunk stored in the vector DB.

```
RagChunk {
  chunk_id:        string  // matches vector store ID
  jurisdiction_id: string
  section_number:  string  // e.g., "§51A-4.217(b)"
  effective_date:  date
  scrape_date:     date
  status:          enum(active | superseded | pending | unknown)
  source_url:      string
  source_publisher: enum(municode | amlegal | city_direct | user_upload)
}
```

**Node: `LegislativeAct`** — the ordinance or bill that created or amended a code section.

```
LegislativeAct {
  ordinance_number: string  // e.g., "Ord. #31234"
  passed_date:      date
  effective_date:   date
  jurisdiction_id:  string
}
```

**Node: `Jurisdiction`**

```
Jurisdiction {
  id:     string
  name:   string
  level:  enum(federal | state | county | city | district)
  parent: Jurisdiction  // enables hierarchical traversal
}
```

**Edges:**

| Relationship | From → To | Meaning |
|---|---|---|
| `SUPERSEDES` | RagChunk → RagChunk | Temporal: newer version replaces older (within same jurisdiction) |
| `PREEMPTS` | Jurisdiction → Jurisdiction | Hierarchical: higher authority overrides lower |
| `GOVERNS` | Jurisdiction → RagChunk | Authority assignment |
| `CREATED` | LegislativeAct → RagChunk | Legislative origin of a section |
| `AMENDED` | LegislativeAct → RagChunk | Legislative amendment to a section |
| `REFERENCES` | RagChunk → RagChunk | Inline cross-citation (e.g., "see §51A-4.120") |

`REFERENCES` edges are extracted at ingestion time — any inline section citation found in a chunk body becomes an edge to the target chunk. This enables graph-traversal retrieval to automatically pull in related sections.

### Provenance Weighting at Retrieval

After vector similarity search returns candidate chunks, apply a **provenance score** before final ranking:

```python
def provenance_weight(chunk: RagChunk) -> float:
    weight = 1.0

    # Hard exclude superseded chunks (or surface with explicit warning)
    if chunk.status == "superseded":
        return 0.0

    # Downweight pending/upcoming effective date chunks
    if chunk.status == "pending":
        weight *= 0.85

    # Stale scrape penalty (configurable threshold)
    age_days = (date.today() - chunk.scrape_date).days
    if age_days > 180:
        weight *= 0.75
    elif age_days > 365:
        weight *= 0.50

    # Downweight user-uploaded source vs. authoritative corpus
    if chunk.source_publisher == "user_upload":
        weight *= 0.80

    return weight

def rerank(candidates: list[tuple[RagChunk, float]]) -> list[tuple[RagChunk, float]]:
    return sorted(
        [(chunk, sim * provenance_weight(chunk)) for chunk, sim in candidates],
        key=lambda x: x[1],
        reverse=True
    )
```

### Distinguishing Supersession Types

Two types of supersession must be tracked separately — they are different edge types with different implications:

- **Temporal supersession** (`SUPERSEDES` edge between `RagChunk` nodes): A newer ordinance amendment replaced an older version of the same section. The old chunk should be excluded from active retrieval but retained for historical queries.
- **Hierarchical supersession** (`PREEMPTS` edge between `Jurisdiction` nodes): A higher-level authority (federal, state) overrides a local rule. This does not remove the local chunk — it adds context that the local rule has a ceiling imposed by a higher authority. Both chunks should surface, with a note on the hierarchy.

### Change Detection Strategy

At scrape time, compute a content hash for each ingested section. On re-scrape, compare hashes. If the hash changes, the existing chunk's status is set to `superseded`, a new chunk is created as `active`, and a `SUPERSEDES` edge is added between them. This creates an append-only amendment history without losing the old version.

---

## 3. Authority Having Jurisdiction (AHJ) Disclaimer

### Problem

Written code and AHJ interpretation diverge in practice. Building department inspectors and plan reviewers within the same city frequently apply the same section differently across projects, neighborhoods, or building types. Interpretive bulletins, policy memos, and informal department precedent are not captured in the ordinance text and are not indexable by this system.

### Recommended Approach

Display a persistent, non-dismissible disclaimer on every result page. It must communicate three things clearly:

1. This tool surfaces the **written ordinance**, not the building department's interpretation of it.
2. The AHJ (the specific city's building department) has final authority over permit decisions.
3. The user should **verify requirements directly with the relevant department** before submitting a permit application or beginning construction.

### Suggested Disclaimer Text

> **Important:** Results are based on published ordinance text and may not reflect current interpretive policy, variance precedents, or informal guidance from the Authority Having Jurisdiction (AHJ). The AHJ — your city's building department — has final authority over all permit decisions. Always verify requirements with the relevant department before proceeding. This tool is a research aid, not a substitute for professional review.

### Implementation Notes

- Include a direct link to the building department contact page or permit portal for the resolved jurisdiction, populated dynamically based on the jurisdiction stack.
- For historic district or conservation overlay results specifically, add a secondary disclaimer noting that these districts often have additional discretionary review processes not captured in code text.
- Log AHJ disclaimer acknowledgement if building a user account system — this is relevant for any future liability posture.

---

## 4. Multi-Permit Compound Project Detection

### Problem

A project description like "adding a detached garage with a bathroom and 200-amp electrical panel" can trigger building, plumbing, electrical, and possibly zoning permits simultaneously. Retrieving code for only one permit type produces an incomplete compliance picture and creates liability for omission.

### Recommended Approach

Before retrieval, classify the project description against a **permit type taxonomy** and identify all applicable permit types. Run separate retrieval passes for each applicable type, then combine and deduplicate results.

### Permit Type Taxonomy (DFW MVP)

| Permit Type | Common Triggers |
|---|---|
| Building | Structural work, additions, new construction, demolition, accessory structures |
| Electrical | New service, panel upgrades, EV charger, rewiring |
| Plumbing | New fixtures, water heater, re-pipe, sewer connection |
| Mechanical (HVAC) | New system, replacement, ductwork, ventilation |
| Zoning / Land Use | Setbacks, lot coverage, use change, variance request |
| Grading / Drainage | Earthwork, retaining walls, impervious surface changes |
| Tree / Landscape | Protected tree removal, required screening |
| Historic Review | Work within a historic or conservation overlay district |
| Sign | Any signage (commercial) |

### Classification Strategy

Use a lightweight LLM classification call before the main retrieval query:

```python
PERMIT_CLASSIFIER_PROMPT = """
Given this project description, identify all permit types that would likely be required.
Return a JSON array of permit type strings from this list:
[building, electrical, plumbing, mechanical, zoning, grading, tree, historic, sign]

Project: {project_description}
Jurisdiction context: {jurisdiction_stack}

Return only the JSON array, no explanation.
"""
```

The jurisdiction stack context matters here: a project in a historic overlay may require historic review even if the description doesn't mention it. Pass the resolved jurisdiction stack to the classifier so overlay-triggered permits are caught.

### Result Presentation

When multiple permit types are detected, present results grouped by permit type with a clear header for each group. Allow the user to expand/collapse each group. Surface a summary at the top: "This project likely requires **3 permits**: Building, Electrical, Zoning."

---

## 5. Document Hierarchy — Corpus Authority vs. User-Uploaded Documents

### Problem

Users need the ability to upload their own documents — both jurisdiction code PDFs (for jurisdictions not yet indexed) and non-ordinance project documents (drawings, specs, surveys). These documents must be handled differently depending on their type, and conflicts between user-uploaded code and the corpus must be resolved predictably and transparently.

### Document Tiers

| Tier | Source | Authority | Storage |
|---|---|---|---|
| **Tier 1 — Corpus** | Scraped from Municode, AML, city sites | Authoritative for ordinance code | Shared vector store + provenance graph |
| **Tier 2 — User Ordinance Upload** | User-provided jurisdiction code PDFs | Supplementary; yields to Tier 1 on conflict | Per-user vector store namespace |
| **Tier 3 — User Project Upload** | Drawings, specs, surveys, photos | Project context only; never ordinance authority | Per-session or per-project store |

### Conflict Resolution — Tier 1 vs. Tier 2

When retrieval returns results from both Tier 1 and Tier 2 that address the same code section:

- **Always surface the Tier 1 (corpus) result** as the primary answer.
- If the Tier 2 document contains conflicting information, surface it as a **secondary reference** with an explicit conflict notice: *"Your uploaded document differs from our indexed ordinance on this section. The indexed version is used."*
- Do not silently discard the Tier 2 content — the conflict itself is useful signal (it may indicate the corpus is stale, or the user has an outdated PDF).
- Log conflicts to a review queue for corpus freshness monitoring.

```python
def resolve_retrieval_conflict(
    corpus_chunk: RagChunk,
    user_chunk: RagChunk
) -> RetrievalResult:
    return RetrievalResult(
        primary=corpus_chunk,
        secondary=user_chunk if conflicts(corpus_chunk, user_chunk) else None,
        conflict_flag=conflicts(corpus_chunk, user_chunk),
        conflict_message=(
            "Your uploaded document differs from the indexed ordinance on this section. "
            "The indexed corpus version is used. If you believe your document is more current, "
            "note the discrepancy when submitting your permit application."
        ) if conflicts(corpus_chunk, user_chunk) else None
    )
```

### Tier 2 — User Ordinance Uploads

- Ingested and chunked identically to corpus documents.
- Stored in a separate vector namespace tagged `source_publisher: user_upload`.
- Assigned `provenance_weight` of 0.80 at retrieval (see Section 2).
- Retrieved only when the corpus has no chunks for that section/jurisdiction, or as supplementary context.
- Users should be warned at upload time: *"Uploaded ordinance documents are used as supplementary references. Our indexed corpus takes precedence for any jurisdiction we have indexed."*

### Tier 3 — User Project Document Uploads

Non-ordinance documents serve a fundamentally different purpose: they provide **project-specific context** to improve the relevance of code retrieval, not ordinance content themselves.

Examples:
- Architectural drawings → extract scope of work, structural elements, square footage, setback distances
- Site surveys → extract parcel dimensions, existing structures, topography
- Soils reports → flag potential grading/drainage permit triggers
- Existing permit documentation → identify previously approved work

These documents should be processed separately from the ordinance pipeline:

- Stored in a per-project context store, not the ordinance vector store.
- Used to **enrich the retrieval query** — extracted project metadata improves the specificity of the ordinance search.
- Clearly labeled in the UI as "Project Documents" and never presented as ordinance authority.
- Consider displaying a badge on any result influenced by project document context: *"Relevant to your uploaded site plan."*

### Namespace Architecture (Docker PostgreSQL + pgvector)

#### Docker Compose Service

Use the official `pgvector` image — it ships with the extension pre-installed, no manual compilation needed.

```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-permit_rag}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB:-permit_rag}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d  # runs *.sql on first boot
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-permit_rag}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

Any `.sql` files placed in `./db/init/` run automatically on first container boot, making it the right place to put the schema below.

#### Connection String

```python
# .env
DATABASE_URL=postgresql://permit_rag:yourpassword@localhost:5432/permit_rag

# When calling from another docker-compose service (e.g., FastAPI app),
# use the service name as the host instead of localhost:
DATABASE_URL=postgresql://permit_rag:yourpassword@postgres:5432/permit_rag
```

#### Full Schema DDL (`./db/init/01_schema.sql`)

```sql
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Supporting enum types
CREATE TYPE jurisdiction_level AS ENUM ('federal', 'state', 'county', 'city', 'district');
CREATE TYPE chunk_status       AS ENUM ('active', 'superseded', 'pending', 'unknown');
CREATE TYPE source_publisher   AS ENUM ('municode', 'amlegal', 'city_direct', 'user_upload');

-- Jurisdictions (hierarchical via parent_id self-reference)
CREATE TABLE IF NOT EXISTS jurisdictions (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    level       jurisdiction_level NOT NULL,
    parent_id   TEXT REFERENCES jurisdictions(id),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Users (minimal — expand as auth grows)
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Projects (groups Tier 3 project documents)
CREATE TABLE IF NOT EXISTS projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Core document chunks table
-- source_tier: 1 = corpus, 2 = user ordinance upload, 3 = user project doc
CREATE TABLE IF NOT EXISTS document_chunks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content          TEXT NOT NULL,
    embedding        VECTOR(1536),        -- adjust dim to match your embedding model

    -- Tier + ownership
    source_tier      INTEGER NOT NULL DEFAULT 1 CHECK (source_tier IN (1, 2, 3)),
    user_id          UUID REFERENCES users(id) ON DELETE CASCADE,   -- NULL for Tier 1
    project_id       UUID REFERENCES projects(id) ON DELETE CASCADE, -- Tier 3 only

    -- Provenance metadata (feeds provenance graph and weighting)
    jurisdiction_id  TEXT REFERENCES jurisdictions(id),
    section_number   TEXT,               -- e.g., "§51A-4.217(b)"
    effective_date   DATE,
    scrape_date      DATE DEFAULT CURRENT_DATE,
    status           chunk_status DEFAULT 'active',
    source_url       TEXT,
    source_publisher source_publisher,
    content_hash     TEXT,               -- SHA-256 of content for change detection

    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for cosine similarity (better recall than IVFFlat, no training step)
CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops);

-- Covering index for the retrieval query filter pattern
CREATE INDEX ON document_chunks (jurisdiction_id, source_tier, status);

-- Partial index for user-scoped lookups (Tiers 2 & 3)
CREATE INDEX ON document_chunks (user_id, source_tier)
    WHERE user_id IS NOT NULL;

-- Change detection index
CREATE INDEX ON document_chunks (content_hash);
```

> **Note:** The embedding dimension (`1536`) matches `text-embedding-3-small`. If you switch models, update this before inserting any data — changing vector dimensions requires dropping and recreating the column and index.

#### Retrieval Query

With raw PostgreSQL (via `asyncpg` or `psycopg2`), parameters are positional (`$1`, `$2`, ...) rather than named. The logic is otherwise identical.

```sql
-- Corpus-first retrieval with per-user Tier 2 supplement
-- $1: query_embedding (vector)
-- $2: jurisdiction_ids (text[])
-- $3: user_id (uuid — pass NULL for unauthenticated queries)

SELECT
    id,
    content,
    source_tier,
    jurisdiction_id,
    section_number,
    effective_date,
    scrape_date,
    status,
    source_publisher,
    1 - (embedding <=> $1) AS similarity
FROM document_chunks
WHERE
    jurisdiction_id = ANY($2)
    AND (
        source_tier = 1                                   -- always include corpus
        OR (source_tier = 2 AND user_id = $3)            -- user's own ordinance uploads
    )
    AND status != 'superseded'
ORDER BY
    source_tier ASC,   -- Tier 1 surfaces before Tier 2 on equal score
    similarity DESC
LIMIT 20;
```

```python
# asyncpg usage (FastAPI + asyncpg)
async def retrieve_chunks(
    conn,
    query_embedding: list[float],
    jurisdiction_ids: list[str],
    user_id: str | None,
) -> list[dict]:
    rows = await conn.fetch(
        RETRIEVAL_QUERY,
        query_embedding,   # $1
        jurisdiction_ids,  # $2
        user_id,           # $3
    )
    return [dict(r) for r in rows]
```

#### Security Model

Without Supabase's Row Level Security, user isolation is enforced **at the application layer**. Key rules to implement in your FastAPI route handlers:

- Never expose a Tier 2/3 chunk to any `user_id` other than its owner.
- Never allow a `user_id` to modify or delete Tier 1 corpus rows.
- Corpus writes (scraper, ingestion pipeline) should connect via a dedicated `corpus_writer` Postgres role with `INSERT`/`UPDATE` on `document_chunks` but no `DELETE`.
- API queries run as a `app_reader` role with `SELECT` only.

```sql
-- Minimal role setup (add to init script)
CREATE ROLE corpus_writer LOGIN PASSWORD 'changeme';
GRANT INSERT, UPDATE ON document_chunks TO corpus_writer;
GRANT SELECT, INSERT ON users, projects TO corpus_writer;

CREATE ROLE app_reader LOGIN PASSWORD 'changeme';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_reader;
```

---

## Summary — Priority Order for MVP

| Priority | Recommendation | MVP Scope |
|---|---|---|
| P0 | Coordinate-based jurisdiction resolution (§1) | Required — zip alone breaks retrieval |
| P0 | AHJ disclaimer (§3) | Required — legal/UX baseline |
| P1 | Graph provenance schema + status tracking (§2) | Implement schema now; full weighting in v1.1 |
| P1 | Document hierarchy + conflict resolution (§5) | Required if user uploads are in MVP scope |
| P2 | Multi-permit compound detection (§4) | Can ship with single-permit, add classifier in v1.1 |

---

*Last updated: based on initial architecture scoping session.*