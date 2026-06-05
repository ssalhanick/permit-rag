"""
db/client.py — psycopg3 connection pool + helper functions
==========================================================
All database access goes through this module.
No other module may issue SQL directly (see AGENTS.md).

Usage:
    from db.client import get_pool, insert_document, insert_chunks, ...
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Generator, Optional
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

# ── Module-level singleton pool ──────────────────────────────

_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    """Return (or create) the module-level connection pool."""
    global _pool
    if _pool is None:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "DATABASE_URL is not set. "
                "Copy .env.example → .env and fill in your credentials."
            )
        _pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
        )
        log.info("Connection pool created (min=1, max=5)")
    return _pool


def close_pool() -> None:
    """Shut down the pool cleanly (call at application exit)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        log.info("Connection pool closed")


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    """Yield a connection from the pool (auto-returns on exit)."""
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


# ════════════════════════════════════════════════
#  JURISDICTIONS
# ════════════════════════════════════════════════

def get_jurisdiction(municipality_id: str) -> Optional[dict[str, Any]]:
    """
    Fetch a jurisdiction row by its id (matches documents.municipality).

    Returns the full row dict (id, name, level, parent_id, dept_name, dept_url)
    or None if not found.
    """
    sql = "SELECT * FROM jurisdictions WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (municipality_id,)).fetchone()


def list_jurisdictions(
    *,
    level: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List all jurisdictions, optionally filtered by level."""
    if level:
        sql = "SELECT * FROM jurisdictions WHERE level = %s ORDER BY level, id;"
        with get_conn() as conn:
            return conn.execute(sql, (level,)).fetchall()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jurisdictions ORDER BY level, id;"
        ).fetchall()


# ════════════════════════════════════════════════
#  DOCUMENTS
# ════════════════════════════════════════════════

def insert_document(
    *,
    doc_id: str,
    source_url: str,
    municipality: str,
    authority_level: str,
    doc_type: str,
    subject_tags: list[str],
    effective_date: Optional[date] = None,
    document_status: str = "active",
    is_current: bool = True,
    retrieval_weight: float = 1.0,
    review_due: Optional[date] = None,
    checksum_sha256: Optional[str] = None,
    source_etag: Optional[str] = None,
    local_path: Optional[str] = None,
    source_tier: int = 1,  # Sprint 1: 1=corpus, 2=user ordinance, 3=project doc
) -> dict[str, Any]:
    """
    Insert a document row. Returns the full row as a dict.

    Uses ON CONFLICT to update metadata if the doc_id already exists,
    which supports re-harvesting without duplicating rows.
    """
    sql = """
        INSERT INTO documents (
            doc_id, source_url, municipality, authority_level,
            doc_type, subject_tags, effective_date, document_status,
            is_current, retrieval_weight, review_due,
            checksum_sha256, source_etag, local_path, source_tier
        ) VALUES (
            %(doc_id)s, %(source_url)s, %(municipality)s,
            %(authority_level)s::authority_level,
            %(doc_type)s::doc_type,
            %(subject_tags)s,
            %(effective_date)s, %(document_status)s::document_status,
            %(is_current)s, %(retrieval_weight)s, %(review_due)s,
            %(checksum_sha256)s, %(source_etag)s, %(local_path)s,
            %(source_tier)s
        )
        ON CONFLICT (doc_id) DO UPDATE SET
            source_url       = EXCLUDED.source_url,
            municipality     = EXCLUDED.municipality,
            authority_level  = EXCLUDED.authority_level,
            doc_type         = EXCLUDED.doc_type,
            subject_tags     = EXCLUDED.subject_tags,
            effective_date   = EXCLUDED.effective_date,
            document_status  = EXCLUDED.document_status,
            is_current       = EXCLUDED.is_current,
            retrieval_weight = EXCLUDED.retrieval_weight,
            review_due       = EXCLUDED.review_due,
            checksum_sha256  = EXCLUDED.checksum_sha256,
            source_etag      = EXCLUDED.source_etag,
            local_path       = EXCLUDED.local_path,
            source_tier      = EXCLUDED.source_tier
        RETURNING *;
    """
    params = {
        "doc_id": doc_id,
        "source_url": source_url,
        "municipality": municipality,
        "authority_level": authority_level,
        "doc_type": doc_type,
        "subject_tags": subject_tags,
        "effective_date": effective_date,
        "document_status": document_status,
        "is_current": is_current,
        "retrieval_weight": retrieval_weight,
        "review_due": review_due,
        "checksum_sha256": checksum_sha256,
        "source_etag": source_etag,
        "local_path": local_path,
        "source_tier": source_tier,  # Sprint 1
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    log.info("Upserted document: %s → %s", doc_id, row["id"])
    return row


def get_document_by_doc_id(doc_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single document row by its human-readable doc_id."""
    sql = "SELECT * FROM documents WHERE doc_id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (doc_id,)).fetchone()


def get_document_by_uuid(uuid: UUID) -> Optional[dict[str, Any]]:
    """Fetch a single document row by its primary key UUID."""
    sql = "SELECT * FROM documents WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (uuid,)).fetchone()


def list_documents(
    *,
    municipality: Optional[str] = None,
    status: Optional[str] = None,
    authority_level: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    List documents with optional municipality/status/authority/doc_type filters.

    Returns all columns, ordered by municipality then doc_id.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if municipality:
        clauses.append("municipality = %(municipality)s")
        params["municipality"] = municipality
    if status:
        clauses.append("document_status = %(status)s::document_status")
        params["status"] = status
    if authority_level:
        clauses.append("authority_level = %(authority_level)s::authority_level")
        params["authority_level"] = authority_level
    if doc_type:
        clauses.append("doc_type = %(doc_type)s::doc_type")
        params["doc_type"] = doc_type

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM documents {where} ORDER BY municipality, doc_id;"

    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def get_document_status_counts(
    *,
    municipality: Optional[str] = None,
    status: Optional[str] = None,
    authority_level: Optional[str] = None,
    doc_type: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return grouped document status counts for optional filters."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if municipality:
        clauses.append("municipality = %(municipality)s")
        params["municipality"] = municipality
    if status:
        clauses.append("document_status = %(status)s::document_status")
        params["status"] = status
    if authority_level:
        clauses.append("authority_level = %(authority_level)s::authority_level")
        params["authority_level"] = authority_level
    if doc_type:
        clauses.append("doc_type = %(doc_type)s::doc_type")
        params["doc_type"] = doc_type

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = (
        "SELECT document_status, count(*) AS count "
        f"FROM documents {where} "
        "GROUP BY document_status "
        "ORDER BY document_status;"
    )
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def update_document_admin_fields(
    doc_id: str,
    *,
    document_status: Optional[str] = None,
    is_current: Optional[bool] = None,
    retrieval_weight: Optional[float] = None,
    review_due: Optional[date] = None,
) -> Optional[dict[str, Any]]:
    """Update mutable governance fields for a single document by doc_id."""
    assignments: list[str] = []
    params: dict[str, Any] = {"doc_id": doc_id}

    if document_status is not None:
        assignments.append("document_status = %(document_status)s::document_status")
        params["document_status"] = document_status
    if is_current is not None:
        assignments.append("is_current = %(is_current)s")
        params["is_current"] = is_current
    if retrieval_weight is not None:
        assignments.append("retrieval_weight = %(retrieval_weight)s")
        params["retrieval_weight"] = retrieval_weight
    if review_due is not None:
        assignments.append("review_due = %(review_due)s")
        params["review_due"] = review_due

    if not assignments:
        return get_document_by_doc_id(doc_id)

    sql = (
        "UPDATE documents "
        f"SET {', '.join(assignments)} "
        "WHERE doc_id = %(doc_id)s "
        "RETURNING *;"
    )
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


def supersede_document(
    old_doc_id: str,
    replacement_doc_id: str,
    *,
    superseded_weight: float = 0.1,
) -> Optional[dict[str, Any]]:
    """Mark old_doc_id as superseded by replacement_doc_id."""
    if old_doc_id == replacement_doc_id:
        raise ValueError("replacement_doc_id must differ from doc_id")

    with get_conn() as conn:
        old_row = conn.execute(
            "SELECT id FROM documents WHERE doc_id = %(doc_id)s;",
            {"doc_id": old_doc_id},
        ).fetchone()
        if old_row is None:
            return None
        replacement_row = conn.execute(
            "SELECT id FROM documents WHERE doc_id = %(doc_id)s;",
            {"doc_id": replacement_doc_id},
        ).fetchone()
        if replacement_row is None:
            raise ValueError(f"Replacement document not found: {replacement_doc_id}")

        updated = conn.execute(
            """
            UPDATE documents
            SET document_status = 'superseded',
                is_current = false,
                retrieval_weight = %(superseded_weight)s,
                superseded_by = %(replacement_id)s
            WHERE doc_id = %(old_doc_id)s
            RETURNING *;
            """,
            {
                "superseded_weight": superseded_weight,
                "replacement_id": replacement_row["id"],
                "old_doc_id": old_doc_id,
            },
        ).fetchone()
        conn.commit()
    return updated


# ════════════════════════════════════════════════
#  CHUNKS
# ════════════════════════════════════════════════

def insert_chunks(
    document_id: UUID,
    chunks: list[dict[str, Any]],
) -> int:
    """
    Bulk-insert text chunks for a document.

    Each dict in *chunks* must have keys:
        chunk_index (int), content (str), char_count (int)
    Optional keys:
        page_start (int), page_end (int)

    Returns the number of rows inserted.
    """
    if not chunks:
        return 0

    sql = """
        INSERT INTO chunks
            (document_id, chunk_index, content, char_count,
             page_start, page_end, content_hash)
        VALUES
            (%(document_id)s, %(chunk_index)s, %(content)s,
             %(char_count)s, %(page_start)s, %(page_end)s,
             %(content_hash)s)
        ON CONFLICT (document_id, chunk_index) DO UPDATE SET
            content      = EXCLUDED.content,
            char_count   = EXCLUDED.char_count,
            page_start   = EXCLUDED.page_start,
            page_end     = EXCLUDED.page_end,
            content_hash = EXCLUDED.content_hash;
    """
    rows: list[dict[str, Any]] = []
    for c in chunks:
        import hashlib
        content = c["content"]
        rows.append({
            "document_id": document_id,
            "chunk_index": c["chunk_index"],
            "content": content,
            "char_count": c["char_count"],
            "page_start": c.get("page_start"),
            "page_end": c.get("page_end"),
            # Sprint 1: compute SHA-256 hash for change detection
            "content_hash": c.get("content_hash") or hashlib.sha256(content.encode()).hexdigest(),
        })

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()

    log.info("Upserted %d chunks for document %s", len(rows), document_id)
    return len(rows)


def delete_chunks_for_document(document_id: UUID) -> int:
    """Delete all chunks belonging to a document. Returns count deleted."""
    sql = "DELETE FROM chunks WHERE document_id = %s;"
    with get_conn() as conn:
        cur = conn.execute(sql, (document_id,))
        conn.commit()
    deleted = cur.rowcount
    log.info("Deleted %d chunks for document %s", deleted, document_id)
    return deleted


def get_chunks_for_document(
    document_id: UUID,
) -> list[dict[str, Any]]:
    """Return all chunks for a document, ordered by chunk_index."""
    sql = """
        SELECT * FROM chunks
        WHERE document_id = %s
        ORDER BY chunk_index;
    """
    with get_conn() as conn:
        return conn.execute(sql, (document_id,)).fetchall()


def count_chunks(document_id: UUID) -> int:
    """Return the number of chunks stored for a document."""
    sql = "SELECT count(*) AS n FROM chunks WHERE document_id = %s;"
    with get_conn() as conn:
        row = conn.execute(sql, (document_id,)).fetchone()
    return row["n"] if row else 0


def match_chunks(
    query_embedding: list[float],
    *,
    top_k: int = 5,
    municipality: Optional[str] = None,
    min_similarity: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Dense vector similarity search via the match_chunks() SQL function.

    Calls the pgvector cosine-distance search defined in db/schema.sql.
    Returns up to *top_k* chunks ordered by source_tier ASC then descending
    similarity (corpus chunks surface before user-uploaded on equal score).

    Args:
        query_embedding: 768-dim float vector (nomic-embed-text query).
        top_k: Maximum number of chunks to return.
        municipality: Optional filter (e.g. "dallas", "plano").
        min_similarity: Discard results below this cosine similarity.

    Returns:
        List of dicts with keys: id, document_id, doc_id, content,
        chunk_index, municipality, authority_level, doc_type,
        document_status, chunk_status, source_tier, ingested_at,
        retrieval_weight, similarity.
    """
    sql = """
        SELECT * FROM match_chunks(
            %(query_embedding)s::vector,
            %(match_count)s,
            %(filter_municipality)s
        );
    """
    params = {
        "query_embedding": str(query_embedding),
        "match_count": top_k,
        "filter_municipality": municipality,
    }
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    # Apply client-side similarity floor
    if min_similarity > 0.0:
        rows = [r for r in rows if r["similarity"] >= min_similarity]

    log.info(
        "match_chunks: %d results (top_k=%d, municipality=%s)",
        len(rows), top_k, municipality,
    )
    return rows


def _search_chunks_with_tsquery(
    query_text: str,
    *,
    top_k: int,
    municipality: Optional[str],
    tsquery_func: str,
) -> list[dict[str, Any]]:
    """Run lexical chunk search using the provided tsquery parser."""
    sql = f"""
        SELECT
            c.id,
            c.document_id,
            d.doc_id,
            c.content,
            c.chunk_index,
            d.municipality,
            d.authority_level,
            d.doc_type,
            d.document_status,
            ts_rank_cd(c.search_vector, {tsquery_func}('english', %(query_text)s)) AS similarity,
            ts_rank_cd(c.search_vector, {tsquery_func}('english', %(query_text)s)) AS bm25_score,
            row_number() OVER (
                ORDER BY ts_rank_cd(c.search_vector, {tsquery_func}('english', %(query_text)s)) DESC,
                c.chunk_index ASC
            ) AS bm25_rank
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.document_status = 'active'
          AND d.is_current = true
          AND c.search_vector @@ {tsquery_func}('english', %(query_text)s)
          AND (%(municipality)s::text IS NULL OR d.municipality = %(municipality)s::text)
        ORDER BY similarity DESC, c.chunk_index ASC
        LIMIT %(top_k)s;
    """
    params = {
        "query_text": query_text,
        "municipality": municipality,
        "top_k": top_k,
    }
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def search_chunks_bm25(
    query_text: str,
    *,
    top_k: int = 5,
    municipality: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Lexical retrieval using chunks.search_vector with BM25-style ranking.

    Returns the same row shape as match_chunks(), where similarity maps to
    ts_rank_cd score for compatibility with downstream ranking.
    """
    try:
        rows = _search_chunks_with_tsquery(
            query_text,
            top_k=top_k,
            municipality=municipality,
            tsquery_func="websearch_to_tsquery",
        )
    except psycopg.Error:
        rows = _search_chunks_with_tsquery(
            query_text,
            top_k=top_k,
            municipality=municipality,
            tsquery_func="plainto_tsquery",
        )
    log.info(
        "search_chunks_bm25: %d results (top_k=%d, municipality=%s)",
        len(rows), top_k, municipality,
    )
    return rows


# ════════════════════════════════════════════════
#  INGESTION VERIFICATIONS
# ════════════════════════════════════════════════

def insert_verification(
    *,
    document_id: UUID,
    stage: str,
    result: str,
    detail: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Log a verification result for an ingestion stage.

    stage:  'download' | 'extraction' | 'chunking' | 'embedding'
    result: 'pass' | 'fail' | 'skip' | 'needs_ocr'
    detail: arbitrary JSON payload with stage-specific metrics
    """
    sql = """
        INSERT INTO ingestion_verifications
            (document_id, stage, result, detail)
        VALUES
            (%(document_id)s,
             %(stage)s::verification_stage,
             %(result)s::verification_result,
             %(detail)s::jsonb)
        RETURNING *;
    """
    import json as _json

    params = {
        "document_id": document_id,
        "stage": stage,
        "result": result,
        "detail": _json.dumps(detail or {}),
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    log.info(
        "Verification: doc=%s stage=%s result=%s",
        document_id, stage, result,
    )
    return row


def get_verifications(
    document_id: UUID,
) -> list[dict[str, Any]]:
    """Return all verification records for a document, newest first."""
    sql = """
        SELECT * FROM ingestion_verifications
        WHERE document_id = %s
        ORDER BY verified_at DESC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (document_id,)).fetchall()


# ════════════════════════════════════════════════
#  QUERY LOG
# ════════════════════════════════════════════════

def insert_query_log(
    *,
    query_text: str,
    model: str,
    municipality: Optional[str] = None,
    top_k: int = 5,
    chunk_ids: Optional[list[UUID]] = None,
    answer_text: Optional[str] = None,
    citations: Optional[list[dict]] = None,
    latency_ms: Optional[int] = None,
) -> dict[str, Any]:
    """Log a RAG query for auditing and evaluation."""
    import json as _json

    sql = """
        INSERT INTO query_log
            (query_text, municipality, top_k, chunk_ids,
             answer_text, citations, model, latency_ms)
        VALUES
            (%(query_text)s, %(municipality)s, %(top_k)s,
             %(chunk_ids)s, %(answer_text)s,
             %(citations)s::jsonb, %(model)s, %(latency_ms)s)
        RETURNING *;
    """
    params = {
        "query_text": query_text,
        "municipality": municipality,
        "top_k": top_k,
        "chunk_ids": chunk_ids or [],
        "answer_text": answer_text,
        "citations": _json.dumps(citations or []),
        "model": model,
        "latency_ms": latency_ms,
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


def insert_purge_audit_log(
    *,
    doc_id: str,
    document_id: UUID,
    actor_identity: str,
    actor_role: str,
    source_tier: int,
    deleted_chunk_count: int,
    local_file_deleted: bool,
) -> dict[str, Any]:
    """Insert one purge audit event row."""
    sql = """
        INSERT INTO purge_audit_log (
            doc_id, document_id, actor_identity, actor_role, source_tier,
            deleted_chunk_count, local_file_deleted
        ) VALUES (
            %(doc_id)s, %(document_id)s, %(actor_identity)s, %(actor_role)s, %(source_tier)s,
            %(deleted_chunk_count)s, %(local_file_deleted)s
        )
        RETURNING *;
    """
    params = {
        "doc_id": doc_id,
        "document_id": document_id,
        "actor_identity": actor_identity,
        "actor_role": actor_role,
        "source_tier": source_tier,
        "deleted_chunk_count": deleted_chunk_count,
        "local_file_deleted": local_file_deleted,
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


# ════════════════════════════════════════════════
#  HEALTH CHECK
# ════════════════════════════════════════════════

def ping() -> bool:
    """Return True if the database is reachable."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1;")
        return True
    except Exception as exc:
        log.error("Database ping failed: %s", exc)
        return False
