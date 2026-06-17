// db/cypher/constraints.cypher — Graph schema constraints and indexes
// =====================================================================
// Apply once after Neo4j starts. Idempotent (IF NOT EXISTS).
//
// Node labels:
//   Document   — one node per permit document (mirrors documents table)
//   Chunk      — one node per text chunk (mirrors chunks table)
//   Municipality — jurisdiction node
//   AuthorityLevel — municipal | county | state | federal
//
// Relationships:
//   (Document)-[:HAS_CHUNK]->(Chunk)
//   (Document)-[:BELONGS_TO]->(Municipality)
//   (Document)-[:GOVERNED_BY]->(AuthorityLevel)
//   (Municipality)-[:PART_OF]->(AuthorityLevel)
//   (Document)-[:SUPERSEDED_BY]->(Document)   // governance lineage

// ── Document constraints ──────────────────────────────────────
CREATE CONSTRAINT document_doc_id IF NOT EXISTS
  FOR (d:Document)
  REQUIRE d.doc_id IS UNIQUE;

CREATE CONSTRAINT document_pg_id IF NOT EXISTS
  FOR (d:Document)
  REQUIRE d.pg_id IS UNIQUE;

// ── Chunk constraints ─────────────────────────────────────────
// Composite uniqueness: one chunk per (document, index).
CREATE CONSTRAINT chunk_pg_id IF NOT EXISTS
  FOR (c:Chunk)
  REQUIRE c.pg_id IS UNIQUE;

// ── Municipality constraints ──────────────────────────────────
CREATE CONSTRAINT municipality_id IF NOT EXISTS
  FOR (m:Municipality)
  REQUIRE m.municipality_id IS UNIQUE;

// ── AuthorityLevel constraints ────────────────────────────────
CREATE CONSTRAINT authority_level_name IF NOT EXISTS
  FOR (a:AuthorityLevel)
  REQUIRE a.name IS UNIQUE;

// ── Indexes for lookup performance ────────────────────────────
CREATE INDEX chunk_doc_id IF NOT EXISTS
  FOR (c:Chunk) ON (c.doc_id);

CREATE INDEX chunk_index IF NOT EXISTS
  FOR (c:Chunk) ON (c.chunk_index);

CREATE INDEX document_municipality IF NOT EXISTS
  FOR (d:Document) ON (d.municipality);

CREATE INDEX document_status IF NOT EXISTS
  FOR (d:Document) ON (d.document_status);
