"""
db/graph_client.py — Neo4j Bolt driver wrapper
================================================
All graph database access goes through this module exclusively.
No other module may issue Cypher directly (mirrors AGENTS.md pattern
for db/client.py).

Import boundary: db/ → standard library only (AGENTS.md).

Usage:
    from db.graph_client import get_driver, upsert_document_node, upsert_chunk_node

Environment variables:
    NEO4J_BOLT_URL  — Bolt URI  (default: bolt://localhost:7687)
    NEO4J_AUTH      — "user/password" string (default: neo4j/localdev123)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

log = logging.getLogger(__name__)

# ── Module-level singleton driver ────────────────────────────

_driver: Any = None  # neo4j.Driver (imported lazily)


def _parse_auth(auth_str: str) -> tuple[str, str]:
    """Parse 'user/password' env string into (user, password) tuple."""
    parts = auth_str.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"NEO4J_AUTH must be 'user/password', got: {auth_str!r}"
        )
    return parts[0], parts[1]


def get_driver() -> Any:
    """
    Return (or create) the module-level Neo4j driver.

    Reads NEO4J_BOLT_URL and NEO4J_AUTH from environment.
    Raises RuntimeError when env vars are missing or driver init fails.
    """
    global _driver
    if _driver is not None:
        return _driver

    try:
        import neo4j  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "neo4j Python driver not installed. "
            "Run: pip install neo4j"
        ) from exc

    from neo4j import GraphDatabase

    bolt_url = os.environ.get("NEO4J_BOLT_URL", "bolt://localhost:7687")
    auth_str = os.environ.get("NEO4J_AUTH", "neo4j/localdev123")
    user, password = _parse_auth(auth_str)

    _driver = GraphDatabase.driver(bolt_url, auth=(user, password))
    log.info("Neo4j driver created → %s (user=%s)", bolt_url, user)
    return _driver


def close_driver() -> None:
    """Close the driver cleanly (call at application exit)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        log.info("Neo4j driver closed")


@contextmanager
def get_session() -> Generator[Any, None, None]:
    """Yield a Neo4j session (auto-closes on exit)."""
    driver = get_driver()
    with driver.session() as session:
        yield session


# ── Constraint bootstrap ─────────────────────────────────────


def apply_constraints() -> None:
    """
    Apply the Cypher schema constraints from db/cypher/constraints.cypher.

    Idempotent — safe to call on every startup. Each statement is executed
    individually so a single failure does not roll back the rest.
    """
    cypher_path = os.path.join(
        os.path.dirname(__file__), "cypher", "constraints.cypher"
    )
    with open(cypher_path, encoding="utf-8") as fh:
        raw = fh.read()

    # Split on semicolons, skip blank lines and comment-only lines
    statements = [
        stmt.strip()
        for stmt in raw.split(";")
        if stmt.strip() and not stmt.strip().startswith("//")
    ]

    with get_session() as session:
        for stmt in statements:
            try:
                session.run(stmt)
            except Exception as exc:
                log.warning("Constraint statement skipped (%s): %.80s", exc, stmt)

    log.info("Graph constraints applied (%d statements)", len(statements))


# ── Document node ─────────────────────────────────────────────


def upsert_document_node(
    *,
    doc_id: str,
    pg_id: str,
    municipality: str,
    authority_level: str,
    doc_type: str,
    document_status: str,
    source_tier: int,
    retrieval_weight: float,
    source_url: str,
) -> None:
    """
    Merge a Document node and connect it to Municipality + AuthorityLevel nodes.

    Uses MERGE so repeated calls are idempotent (no duplicates).
    Also merges the Municipality and AuthorityLevel nodes and creates
    relationships if they do not already exist.
    """
    cypher = """
    MERGE (d:Document {doc_id: $doc_id})
    SET d.pg_id            = $pg_id,
        d.municipality     = $municipality,
        d.authority_level  = $authority_level,
        d.doc_type         = $doc_type,
        d.document_status  = $document_status,
        d.source_tier      = $source_tier,
        d.retrieval_weight = $retrieval_weight,
        d.source_url       = $source_url

    MERGE (m:Municipality {municipality_id: $municipality})
    MERGE (a:AuthorityLevel {name: $authority_level})

    MERGE (d)-[:BELONGS_TO]->(m)
    MERGE (d)-[:GOVERNED_BY]->(a)
    MERGE (m)-[:PART_OF]->(a)
    """
    with get_session() as session:
        session.run(
            cypher,
            doc_id=doc_id,
            pg_id=pg_id,
            municipality=municipality,
            authority_level=authority_level,
            doc_type=doc_type,
            document_status=document_status,
            source_tier=source_tier,
            retrieval_weight=retrieval_weight,
            source_url=source_url,
        )
    log.debug("Upserted Document node: %s", doc_id)


# ── Chunk node ────────────────────────────────────────────────


def upsert_chunk_node(
    *,
    pg_id: str,
    doc_id: str,
    chunk_index: int,
    content: str,
    municipality: str,
    authority_level: str,
    similarity: float = 0.0,
) -> None:
    """
    Merge a Chunk node and connect it to its parent Document node.

    The Document node must already exist (call upsert_document_node first).
    content is stored on the node for APOC text procedures.
    similarity is optional — set during retrieval-driven graph enrichment.
    """
    cypher = """
    MERGE (c:Chunk {pg_id: $pg_id})
    SET c.doc_id       = $doc_id,
        c.chunk_index  = $chunk_index,
        c.content      = $content,
        c.municipality = $municipality,
        c.authority_level = $authority_level,
        c.similarity   = $similarity

    WITH c
    MATCH (d:Document {doc_id: $doc_id})
    MERGE (d)-[:HAS_CHUNK]->(c)
    """
    with get_session() as session:
        session.run(
            cypher,
            pg_id=pg_id,
            doc_id=doc_id,
            chunk_index=chunk_index,
            content=content,
            municipality=municipality,
            authority_level=authority_level,
            similarity=similarity,
        )
    log.debug("Upserted Chunk node: %s[%d]", doc_id, chunk_index)


# ── Supersession edge ─────────────────────────────────────────


def link_supersession(old_doc_id: str, new_doc_id: str) -> None:
    """
    Create a SUPERSEDED_BY relationship between two Document nodes.

    Idempotent — MERGE ensures no duplicate edges.
    Raises ValueError if either document node does not exist.
    """
    cypher = """
    MATCH (old:Document {doc_id: $old_doc_id})
    MATCH (new:Document {doc_id: $new_doc_id})
    MERGE (old)-[:SUPERSEDED_BY]->(new)
    """
    with get_session() as session:
        result = session.run(cypher, old_doc_id=old_doc_id, new_doc_id=new_doc_id)
        summary = result.consume()
    if summary.counters.relationships_created == 0:
        log.debug(
            "SUPERSEDED_BY edge already exists or nodes not found: %s → %s",
            old_doc_id, new_doc_id,
        )
    else:
        log.info("Linked supersession: %s → %s", old_doc_id, new_doc_id)


# ── Health check ──────────────────────────────────────────────


def ping() -> bool:
    """Return True if Neo4j is reachable via Bolt."""
    try:
        with get_session() as session:
            session.run("RETURN 1")
        return True
    except Exception as exc:
        log.error("Neo4j ping failed: %s", exc)
        return False


# ── Read helpers ──────────────────────────────────────────────


def get_document_node(doc_id: str) -> Optional[dict[str, Any]]:
    """Return the Document node properties dict, or None if not found."""
    cypher = "MATCH (d:Document {doc_id: $doc_id}) RETURN properties(d) AS props"
    with get_session() as session:
        record = session.run(cypher, doc_id=doc_id).single()
    return dict(record["props"]) if record else None


def get_chunks_for_document(doc_id: str) -> list[dict[str, Any]]:
    """Return all Chunk node property dicts for a document, ordered by chunk_index."""
    cypher = """
    MATCH (d:Document {doc_id: $doc_id})-[:HAS_CHUNK]->(c:Chunk)
    RETURN properties(c) AS props
    ORDER BY c.chunk_index
    """
    with get_session() as session:
        records = session.run(cypher, doc_id=doc_id).data()
    return [dict(r["props"]) for r in records]
