# Session: 2026-05-20 (evening)

## Type

Foundation session — project scaffold, dependencies, database schema deployed.

## Goal

Complete week 1 checklist: GitHub repo, pyproject.toml, .env.example,
Supabase/Postgres project, db/schema.sql.

---

## Completed

### GitHub repo created and pushed

- Initialized git in permit_rag directory
- Remote: git@github.com:ssalhanick/permit-rag.git
- Resolved merge conflict with GitHub-generated README (kept local)
- Initial commit includes full project scaffold

### pyproject.toml written

- Replaces requirements.txt as single source of truth for dependencies
- Core deps: requests, beautifulsoup4, rich, psycopg3, pgvector,
  anthropic, pypdf, langchain-text-splitters, fastapi, uvicorn,
  python-dotenv, pydantic, pydantic-settings
- Optional groups: dev (pytest, ruff, mypy, pre-commit), eval (ragas)
- Tool configs: ruff (py311, 88-char lines), mypy (strict), pytest

### .env.example written

- Single DATABASE_URL for local Postgres connection
- ANTHROPIC_API_KEY, LLM_MODEL, EMBEDDING_MODEL
- Budget guards: HARVEST_BUDGET_USD, EMBED_BUDGET_USD

### Architecture decision: local Postgres over Supabase

- Supabase free tier pauses after 7 days of inactivity — bad for dev
- Local Postgres gives unlimited size, always on, zero internet dependency
- Schema is pure Postgres + pgvector — portable to Supabase or RDS later
- Swapped supabase/vecs SDK for psycopg3 + pgvector Python package
- No vendor lock-in; connection string swap is the only migration step

### Docker Compose for Postgres + pgvector

- docker-compose.yml using pgvector/pgvector:pg17 image
- schema.sql auto-runs on first start via initdb.d mount
- Data persists in named volume (pgdata)
- Postgres 18 installed locally, but Docker uses pg17 (pgvector
  doesn't have a pg18 image yet)

### db/schema.sql deployed and verified

- 4 tables confirmed: documents, chunks, ingestion_verifications, query_log
- pgvector extension enabled, HNSW index on chunks.embedding
- match_chunks() RPC function for vector similarity search
- RLS enabled on all tables with service_role bypass policies
- Enums: authority_level, document_status, doc_type,
  verification_stage, verification_result
- updated_at trigger on documents table

### .gitignore expanded

- Added coverage for ruff, mypy, pytest caches
- Added IDE directories (.vscode, .idea)
- Existing AGENTS.md rules preserved (no .env, documents/raw/,
  __pycache__, node_modules)

---

## Files changed

- pyproject.toml (created)
- .env.example (rewritten — local Postgres, not Supabase)
- db/schema.sql (rewritten — full schema with enums, RLS, HNSW index)
- docker-compose.yml (created)
- .gitignore (expanded for new tooling)
- STATE.md (updated — db ✅, new decisions, task queue advanced)
- AGENTS.md (user added git rule: all git commands run manually)

## Files NOT changed

- ingestion/harvester.py
- db/client.py (still empty — next session)
- rag/ (not started)

---

## Decisions made

- Local Postgres 18 + pgvector for dev over hosted Supabase
- psycopg3 (direct driver) over Supabase Python SDK
- Docker Compose for local database (pgvector/pgvector:pg17)
- Voyage-3 embeddings → 1024 dimensions → vector(1024) column type
- HNSW index (m=16, ef_construction=64) for vector search

---

## Next session should

1. Write db/client.py — psycopg3 connection pool, insert/query helpers
2. Write ingestion/chunker.py + ingestion/verification.py together
3. Run harvester.py against live URLs, verify all 15 docs download
4. pip install -e ".[dev]" and confirm all deps resolve
