# Session: 2026-05-19

## Type

Pre-class design and research session — no code deployed,
no database touched. This is the conceptual foundation that
informs all June 1+ build sessions.

## Goal

Research viable AI/ML business verticals, select one, and
design the full technical and business architecture before
the entrepreneurship course begins June 1.

---

## Completed

### Business Design

- Evaluated 10+ RAG/ML vertical opportunities across medical,
  construction, franchise, municipal, maritime, agriculture,
  and others
- Selected DFW construction permitting as optimal MVP vertical:
  all docs free and public, fast contractor sales cycles,
  Dallas construction boom creates urgent local demand,
  no HIPAA complexity, in-person demo advantage
- Defined two customer paths: sell to contractors ($149/month)
  and sell to cities (longer cycle, higher value)
- Mapped $10k seed budget across legal, infra, API costs,
  sales, and $4,600 reserve
- Built 9-week timeline (June 1 — August 1) with free path
  and seed-money-accelerated path side by side

### Technical Architecture

- Designed full AWS HIPAA-compliant RAG infrastructure
  (applicable to medical vertical if we expand later):
  Cognito → API Gateway → Lambda → Aurora+pgvector →
  Bedrock → Kinesis → S3 tiered storage → Athena
- Designed document governance system:
  metadata schema (doc_id, municipality, authority_level,
  doc_type, effective_date, document_status, retrieval_weight,
  review_due, checksum, source_etag)
  supersession chain (active → superseded → repealed)
  temporal scoring at retrieval time
  ETag-based source change detection
  review_due scheduling by doc_type (30–365 days)
  conflict detection between retrieved chunks
  answer provenance logging (audit trail per answer)
- Designed RAGAs evaluation framework integration:
  four metrics: faithfulness, answer_relevancy,
  context_precision, context_recall
  target scores before any demo: faithfulness 0.85+
  eval dataset strategy: auto-generate + contractor validation
  cost: under $15/month to run continuously
- Designed tiered audit log storage:
  hot (S3 Standard, 0–90 days)
  warm (S3 IA, 90 days–2 years)
  cold (S3 Glacier IR, 2–6 years)
  Athena + Glue for partitioned queries
  partitioning strategy: customer_id / year / month / day

### Project Structure

- Defined full permit_rag/ folder tree:
  ingestion/, rag/, evaluation/, db/, api/, frontend/,
  audit/, infra/, documents/, tests/, scripts/
- Resolved **init**.py placement rules:
  add to any directory another Python file imports from,
  skip for JSON/SQL/data-only directories
- Established AGENTS.md + STATE.md + journals/ system:
  AGENTS.md = global rules constitution (rarely changes)
  STATE.md = minimal live state (max 30 seconds to read)
  journals/ = append-only session log (never edit past entries)

### Document Sources Identified

- Municode.com — primary source for all DFW city codes
  (Dallas, Plano, Frisco, McKinney, Fort Worth)
- TDLR — Texas contractor licensing, accessibility standards
- OSHA 1926, ADA 2010, EPA NPDES — federal layer
- Full URL list documented and catalogued in harvester.py

### Files Written (not yet deployed or run)

- ingestion/harvester.py — full DFW document harvester
  with metadata tagging, checksum dedup, ETag monitoring,
  supersession chain, review scheduling, registry output
- requirements.txt
- README.md (harvester docs)
- AGENTS.md
- STATE.md
- journals/session_2026-06-01.md (placeholder for week 1)

---

## Not completed

- pyproject.toml
- .env.example
- db/schema.sql
- Supabase project not created
- harvester.py not actually run against live URLs yet
- No vectors in any database yet
- No API, frontend, or eval pipeline

---

## Key decisions made

| Decision   | Choice                      | Rationale                                   |
| ---------- | --------------------------- | ------------------------------------------- |
| Vertical   | DFW construction permitting | Free docs, fast sales, local advantage      |
| Vector DB  | Supabase + pgvector         | BAA-eligible, cheaper than Pinecone at MVP  |
| LLM        | Claude API via Anthropic    | Single vendor, BAA path, citation quality   |
| Backend    | FastAPI                     | Async, auto OpenAPI docs, easy deploy       |
| Frontend   | Vite + React                | Simple, free Vercel deploy, no SSR needed   |
| Local dev  | Chroma                      | No Supabase dependency during dev iteration |
| Embeddings | Claude API                  | Consistency with generation model           |
| Eval       | RAGAs                       | Purpose-built for RAG, cheap to run         |
| Auth       | Supabase Auth               | Free tier, JWT, RBAC built in               |
| Audit logs | Kinesis → S3 → Athena       | Scales cheaply, HIPAA-ready pattern         |

---

## Open questions going into June 1

- Reranker: Cohere API vs local cross-encoder model?
- Municipality filter: dropdown UI or free-text parsing?
- Should harvester run on a Lambda schedule from day one
  or stay as a local cron until first paying customer?

---

## Next session should (June 1, week 1)

1. Create GitHub repo, push initial structure
2. Write pyproject.toml and .env.example
3. Create Supabase project (hosted)
4. Write and deploy db/schema.sql
5. Run harvester.py against live DFW URLs, verify 14 docs download
6. Start ingestion/chunker.py

## Next session prompt

Read AGENTS.md, STATE.md, and journals/session_2026-05-19.md.
Follow all rules in AGENTS.md without exception.
Today is June 1, week 1. Task: create GitHub repo, write
pyproject.toml and .env.example, create Supabase project,
write db/schema.sql.
