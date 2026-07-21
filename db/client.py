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
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

# ── Module-level singleton pool ──────────────────────────────

_pool: ConnectionPool | None = None


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

def get_jurisdiction(municipality_id: str) -> dict[str, Any] | None:
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
    level: str | None = None,
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
    effective_date: date | None = None,
    document_status: str = "active",
    is_current: bool = True,
    retrieval_weight: float = 1.0,
    review_due: date | None = None,
    checksum_sha256: str | None = None,
    source_etag: str | None = None,
    local_path: str | None = None,
    source_tier: int = 1,  # Sprint 1: 1=corpus, 2=user ordinance, 3=project doc
    project_id: UUID | None = None,
    uploaded_by: UUID | None = None,
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
            checksum_sha256, source_etag, local_path, source_tier,
            project_id, uploaded_by
        ) VALUES (
            %(doc_id)s, %(source_url)s, %(municipality)s,
            %(authority_level)s::authority_level,
            %(doc_type)s::doc_type,
            %(subject_tags)s,
            %(effective_date)s, %(document_status)s::document_status,
            %(is_current)s, %(retrieval_weight)s, %(review_due)s,
            %(checksum_sha256)s, %(source_etag)s, %(local_path)s,
            %(source_tier)s, %(project_id)s, %(uploaded_by)s
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
            source_tier      = EXCLUDED.source_tier,
            project_id       = EXCLUDED.project_id,
            uploaded_by      = EXCLUDED.uploaded_by
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
        "project_id": project_id,
        "uploaded_by": uploaded_by,
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    log.info("Upserted document: %s → %s", doc_id, row["id"])
    return row


def get_document_by_doc_id(doc_id: str) -> dict[str, Any] | None:
    """Fetch a single document row by its human-readable doc_id."""
    sql = "SELECT * FROM documents WHERE doc_id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (doc_id,)).fetchone()


def get_document_by_uuid(uuid: UUID) -> dict[str, Any] | None:
    """Fetch a single document row by its primary key UUID."""
    sql = "SELECT * FROM documents WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (uuid,)).fetchone()


def list_documents(
    *,
    municipality: str | None = None,
    status: str | None = None,
    authority_level: str | None = None,
    doc_type: str | None = None,
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
    municipality: str | None = None,
    status: str | None = None,
    authority_level: str | None = None,
    doc_type: str | None = None,
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
    document_status: str | None = None,
    is_current: bool | None = None,
    retrieval_weight: float | None = None,
    review_due: date | None = None,
) -> dict[str, Any] | None:
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
) -> dict[str, Any] | None:
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
#  SOURCE IDENTITY (migration 022 — on-demand URL pull)
# ════════════════════════════════════════════════

def find_document_by_source_url_norm(url_normalized: str) -> dict[str, Any] | None:
    """Fetch the current document matching a normalized source URL."""
    sql = """
        SELECT * FROM documents
        WHERE source_url_normalized = %s AND is_current = true
        ORDER BY ingested_at DESC
        LIMIT 1;
    """
    with get_conn() as conn:
        return conn.execute(sql, (url_normalized,)).fetchone()


def find_document_by_fallback_identity(
    municipality: str,
    doc_type: str,
    source_filename: str,
) -> dict[str, Any] | None:
    """Fetch the current document matching the fallback identity key."""
    sql = """
        SELECT * FROM documents
        WHERE municipality = %s
          AND doc_type = %s::doc_type
          AND source_filename = %s
          AND is_current = true
        ORDER BY ingested_at DESC
        LIMIT 1;
    """
    with get_conn() as conn:
        return conn.execute(sql, (municipality, doc_type, source_filename)).fetchone()


def find_document_by_checksum(checksum_sha256: str) -> dict[str, Any] | None:
    """Fetch any current document whose bytes match *checksum_sha256*."""
    sql = """
        SELECT * FROM documents
        WHERE checksum_sha256 = %s AND is_current = true
        ORDER BY ingested_at DESC
        LIMIT 1;
    """
    with get_conn() as conn:
        return conn.execute(sql, (checksum_sha256,)).fetchone()


def set_document_source_identity(
    doc_id: str,
    *,
    source_url_normalized: str | None = None,
    source_filename: str | None = None,
    url_changed_flag: bool | None = None,
    touch_last_pulled: bool = False,
) -> dict[str, Any] | None:
    """Update identity/audit columns (migration 022) for one document."""
    assignments: list[str] = []
    params: dict[str, Any] = {"doc_id": doc_id}

    if source_url_normalized is not None:
        assignments.append("source_url_normalized = %(source_url_normalized)s")
        params["source_url_normalized"] = source_url_normalized
    if source_filename is not None:
        assignments.append("source_filename = %(source_filename)s")
        params["source_filename"] = source_filename
    if url_changed_flag is not None:
        assignments.append("url_changed_flag = %(url_changed_flag)s")
        params["url_changed_flag"] = url_changed_flag
    if touch_last_pulled:
        assignments.append("last_pulled_at = now()")

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
    municipality: str | None = None,
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


def match_project_chunks(
    query_embedding: list[float],
    *,
    project_id: UUID,
    top_k: int = 5,
    min_similarity: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Vector search limited to tier 2/3 documents for a project.

    Includes docs with documents.project_id or linked via project_documents.

    Args:
        query_embedding: 768-dim query vector.
        project_id: Project scope UUID.
        top_k: Max results.
        min_similarity: Cosine similarity floor.

    Returns:
        Chunk dicts ordered by source_tier ASC, similarity DESC.
    """
    sql = """
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
            c.status AS chunk_status,
            d.source_tier,
            d.ingested_at,
            d.retrieval_weight,
            1 - (c.embedding <=> %(query_embedding)s::vector) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN project_documents pd ON pd.document_id = d.id
        WHERE d.source_tier IN (2, 3)
          AND d.document_status = 'active'
          AND c.status = 'active'
          AND c.embedding IS NOT NULL
          AND (d.project_id = %(project_id)s OR pd.project_id = %(project_id)s)
        ORDER BY d.source_tier ASC, similarity DESC
        LIMIT %(match_count)s;
    """
    params = {
        "query_embedding": str(query_embedding),
        "project_id": project_id,
        "match_count": top_k,
    }
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    if min_similarity > 0.0:
        rows = [r for r in rows if r["similarity"] >= min_similarity]
    log.info("match_project_chunks: %d results (project_id=%s)", len(rows), project_id)
    return rows


def get_chunks_by_ids(chunk_ids: list[UUID]) -> list[dict[str, Any]]:
    """
    Load chunk rows by primary key for mobile chunk-ID generation path.

    Args:
        chunk_ids: Chunk UUIDs from on-device retrieval.

    Returns:
        Chunk dicts with document metadata.
    """
    if not chunk_ids:
        return []
    sql = """
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
            c.status AS chunk_status,
            d.source_tier,
            d.ingested_at,
            d.retrieval_weight,
            1.0 AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.id = ANY(%(chunk_ids)s)
          AND d.document_status = 'active'
          AND c.status = 'active';
    """
    with get_conn() as conn:
        return conn.execute(sql, {"chunk_ids": chunk_ids}).fetchall()


def list_corpus_sync_chunks(
    *,
    municipality: str | None = None,
    limit: int = 500,
    include_embeddings: bool = False,
) -> list[dict[str, Any]]:
    """
    Export tier-1 corpus chunks for on-device cache sync.

    Args:
        municipality: Optional municipality filter.
        limit: Max rows (mobile bundle budget).
        include_embeddings: Include 768-dim vectors when True.

    Returns:
        Lightweight chunk dicts for mobile SQLite cache.
    """
    embed_col = "c.embedding::text AS embedding_text" if include_embeddings else "NULL AS embedding_text"
    sql = f"""
        SELECT
            c.id,
            d.doc_id,
            c.chunk_index,
            LEFT(c.content, 800) AS content,
            d.municipality,
            d.source_tier,
            {embed_col}
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.source_tier = 1
          AND d.document_status = 'active'
          AND c.status = 'active'
          AND c.embedding IS NOT NULL
          AND (%(municipality)s IS NULL OR d.municipality = %(municipality)s)
        ORDER BY d.doc_id, c.chunk_index
        LIMIT %(limit)s;
    """
    with get_conn() as conn:
        return conn.execute(sql, {
            "municipality": municipality,
            "limit": limit,
        }).fetchall()


def _search_chunks_with_tsquery(
    query_text: str,
    *,
    top_k: int,
    municipality: str | None,
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
          AND c.status = 'active'
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
    municipality: str | None = None,
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
    detail: dict[str, Any] | None = None,
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
    municipality: str | None = None,
    top_k: int = 5,
    chunk_ids: list[UUID] | None = None,
    answer_text: str | None = None,
    citations: list[dict] | None = None,
    latency_ms: int | None = None,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
) -> dict[str, Any]:
    """Log a RAG query for auditing and evaluation."""
    import json as _json

    sql = """
        INSERT INTO query_log
            (query_text, municipality, top_k, chunk_ids,
             answer_text, citations, model, latency_ms, user_id, project_id)
        VALUES
            (%(query_text)s, %(municipality)s, %(top_k)s,
             %(chunk_ids)s, %(answer_text)s,
             %(citations)s::jsonb, %(model)s, %(latency_ms)s,
             %(user_id)s, %(project_id)s)
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
        "user_id": user_id,
        "project_id": project_id,
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


# ════════════════════════════════════════════════
#  USERS (Cognito-backed, Sprint 11)
# ════════════════════════════════════════════════

import random
import re
import string


def _derive_username(email: str) -> str:
    """
    Derive a clean, DB-safe username from an email address prefix.
    Strips non-alphanumeric chars and trims to 28 characters.
    """
    prefix = email.split("@")[0].lower()
    clean = re.sub(r"[^a-z0-9_.\-]", "_", prefix)[:28].strip("_.-")
    return clean if len(clean) >= 2 else "user"


def _rand_suffix(n: int = 4) -> str:
    """Return a short random alphanumeric suffix."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def get_or_create_cognito_user(
    cognito_sub: str,
    email: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """
    Look up a user by Cognito sub. On first login, create the RDS row.

    Falls back to email lookup to handle Cognito account linking (e.g. a user
    who registered with email+password and later signs in via Google with the
    same address — Cognito may issue a new sub if accounts are not linked).
    """
    norm_email = email.lower().strip()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE cognito_sub = %s AND is_active = true;",
            (cognito_sub,),
        ).fetchone()
        if row:
            return row

        # Email-based fallback (catches Cognito account-linking edge case)
        row = conn.execute(
            "SELECT * FROM users WHERE email = %s AND is_active = true;",
            (norm_email,),
        ).fetchone()
        if row:
            # Adopt the new Cognito sub for this account
            conn.execute(
                "UPDATE users SET cognito_sub = %s WHERE id = %s;",
                (cognito_sub, row["id"]),
            )
            conn.commit()
            return dict(row) | {"cognito_sub": cognito_sub}

    # New user — derive a username, retry with random suffix on conflict
    base = _derive_username(display_name or norm_email)
    for attempt in range(6):
        suffix = "" if attempt == 0 else f"_{_rand_suffix()}"
        username = (base + suffix)[:30]
        sql_insert = """
            INSERT INTO users (username, email, cognito_sub, role)
            VALUES (%(username)s, %(email)s, %(cognito_sub)s, 'member')
            RETURNING *;
        """
        try:
            with get_conn() as conn:
                row = conn.execute(sql_insert, {
                    "username": username,
                    "email": norm_email,
                    "cognito_sub": cognito_sub,
                }).fetchone()
                conn.commit()
            log.info("Created cognito user: %s (sub=%.8s…)", username, cognito_sub)
            return row
        except Exception:
            if attempt == 5:
                raise
            continue

    raise RuntimeError("Failed to create user after 6 attempts.")  # unreachable


def get_user_by_id(user_id: UUID) -> dict[str, Any] | None:
    """Fetch active user row by primary key UUID."""
    sql = "SELECT * FROM users WHERE id = %s AND is_active = true;"
    with get_conn() as conn:
        return conn.execute(sql, (user_id,)).fetchone()


def deactivate_user(user_id: UUID) -> dict[str, Any] | None:
    """Soft-delete user: set is_active=False."""
    sql = "UPDATE users SET is_active = false WHERE id = %s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, (user_id,)).fetchone()
        conn.commit()
    return row


# ════════════════════════════════════════════════
#  PROJECTS (Sprint 9)
# ════════════════════════════════════════════════

class UnsetType:
    """Sentinel type for unset values in updates."""
    pass

UNSET = UnsetType()


def create_project(
    *,
    name: str,
    owner_user_id: UUID,
    description: str | None = None,
    municipality: str | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    historic_district: str | None = None,
    conservation_district: str | None = None,
    spaces: list[str] | None = None,
    work_types: list[str] | None = None,
    materials: list[str] | None = None,
    recommended_permits: list[str] | None = None,
    budget: str | None = None,
    persona: str | None = None,
    custom_system_prompt: str | None = None,
) -> dict[str, Any]:
    """Create a project and auto-enroll the owner in one transaction."""
    import json as _json

    sql_project = """
        INSERT INTO projects (
            name, owner_user_id, description, municipality,
            address, latitude, longitude, historic_district, conservation_district,
            spaces, work_types, materials, recommended_permits, budget, persona, custom_system_prompt
        )
        VALUES (
            %(name)s, %(owner_user_id)s, %(description)s, %(municipality)s,
            %(address)s, %(latitude)s, %(longitude)s, %(historic_district)s, %(conservation_district)s,
            %(spaces)s, %(work_types)s, %(materials)s, %(recommended_permits)s, %(budget)s, %(persona)s, %(custom_system_prompt)s
        )
        RETURNING *;
    """
    sql_member = """
        INSERT INTO project_members (project_id, user_id, role)
        VALUES (%(project_id)s, %(user_id)s, 'owner');
    """
    with get_conn() as conn:
        row = conn.execute(sql_project, {
            "name": name,
            "owner_user_id": owner_user_id,
            "description": description,
            "municipality": municipality,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "historic_district": historic_district,
            "conservation_district": conservation_district,
            "spaces": _json.dumps(spaces) if spaces is not None else None,
            "work_types": _json.dumps(work_types) if work_types is not None else None,
            "materials": _json.dumps(materials) if materials is not None else None,
            "recommended_permits": _json.dumps(recommended_permits) if recommended_permits is not None else None,
            "budget": budget,
            "persona": persona,
            "custom_system_prompt": custom_system_prompt,
        }).fetchone()
        conn.execute(sql_member, {"project_id": row["id"], "user_id": owner_user_id})
        conn.commit()
    log.info("Created project: %s (owner=%s)", name, owner_user_id)
    return row


def get_project(project_id: UUID) -> dict[str, Any] | None:
    """Fetch project by UUID (excludes soft-deleted; archived projects still resolve)."""
    sql = "SELECT * FROM projects WHERE id = %s AND deleted_at IS NULL;"
    with get_conn() as conn:
        return conn.execute(sql, (project_id,)).fetchone()


def list_projects_for_user(
    user_id: UUID,
    *,
    status: str | None = None,
    search: str | None = None,
    has_room_scans: bool | None = None,
) -> list[dict[str, Any]]:
    """Projects where user is a member (any role), filterable for the projects browser.

    status: "ongoing" (not archived), "archived", "deleted" (soft-deleted trash view),
    or None for everything not soft-deleted (ongoing + archived).
    """
    where = ["pm.user_id = %(user_id)s"]
    params: dict[str, Any] = {"user_id": user_id}

    if status == "deleted":
        where.append("p.deleted_at IS NOT NULL")
    else:
        where.append("p.deleted_at IS NULL")
        if status == "ongoing":
            where.append("p.is_archived = false")
        elif status == "archived":
            where.append("p.is_archived = true")

    if search:
        where.append(
            "(p.name ILIKE %(search)s OR p.address ILIKE %(search)s OR p.municipality ILIKE %(search)s)"
        )
        params["search"] = f"%{search}%"

    if has_room_scans is not None:
        exists_clause = """
            EXISTS (
                SELECT 1 FROM project_room_scan_links l
                WHERE l.project_id = p.id
            )
        """
        where.append(exists_clause if has_room_scans else f"NOT {exists_clause}")

    sql = f"""
        SELECT p.*
        FROM projects p
        JOIN project_members pm ON pm.project_id = p.id
        WHERE {' AND '.join(where)}
        ORDER BY p.created_at DESC;
    """
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def update_project(
    project_id: UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    municipality: str | None = None,
    address: str | None = None,
    latitude: float | None | UnsetType = UNSET,
    longitude: float | None | UnsetType = UNSET,
    historic_district: str | None | UnsetType = UNSET,
    conservation_district: str | None | UnsetType = UNSET,
    spaces: list[str] | None = None,
    work_types: list[str] | None = None,
    materials: list[str] | None = None,
    recommended_permits: list[str] | None = None,
    room_summary: dict[str, Any] | None = None,
    budget: str | None = None,
    persona: str | None = None,
    custom_system_prompt: str | None = None,
) -> dict[str, Any] | None:
    """Update mutable project fields."""
    import json as _json

    assignments: list[str] = []
    params: dict[str, Any] = {"id": project_id}
    if name is not None:
        assignments.append("name = %(name)s")
        params["name"] = name
    if description is not None:
        assignments.append("description = %(description)s")
        params["description"] = description
    if municipality is not None:
        assignments.append("municipality = %(municipality)s")
        params["municipality"] = municipality
    if address is not None:
        assignments.append("address = %(address)s")
        params["address"] = address
    if latitude is not UNSET:
        assignments.append("latitude = %(latitude)s")
        params["latitude"] = latitude
    if longitude is not UNSET:
        assignments.append("longitude = %(longitude)s")
        params["longitude"] = longitude
    if historic_district is not UNSET:
        assignments.append("historic_district = %(historic_district)s")
        params["historic_district"] = historic_district
    if conservation_district is not UNSET:
        assignments.append("conservation_district = %(conservation_district)s")
        params["conservation_district"] = conservation_district
    if spaces is not None:
        assignments.append("spaces = %(spaces)s::jsonb")
        params["spaces"] = _json.dumps(spaces)
    if work_types is not None:
        assignments.append("work_types = %(work_types)s::jsonb")
        params["work_types"] = _json.dumps(work_types)
    if materials is not None:
        assignments.append("materials = %(materials)s::jsonb")
        params["materials"] = _json.dumps(materials)
    if recommended_permits is not None:
        assignments.append("recommended_permits = %(recommended_permits)s::jsonb")
        params["recommended_permits"] = _json.dumps(recommended_permits)
    if room_summary is not None:
        assignments.append("room_summary = %(room_summary)s::jsonb")
        params["room_summary"] = _json.dumps(room_summary)
    if budget is not None:
        assignments.append("budget = %(budget)s")
        params["budget"] = budget
    if persona is not None:
        assignments.append("persona = %(persona)s")
        params["persona"] = persona
    if custom_system_prompt is not None:
        assignments.append("custom_system_prompt = %(custom_system_prompt)s")
        params["custom_system_prompt"] = custom_system_prompt
    if not assignments:
        return get_project(project_id)
    sql = f"UPDATE projects SET {', '.join(assignments)} WHERE id = %(id)s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


def transfer_project_ownership(project_id: UUID, new_owner_id: UUID) -> dict[str, Any] | None:
    """Transfer ownership atomically: projects.owner_user_id and project_members roles."""
    with get_conn() as conn:
        proj = conn.execute("SELECT owner_user_id FROM projects WHERE id = %s;", (project_id,)).fetchone()
        if not proj:
            return None
        old_owner_id = proj["owner_user_id"]
        conn.execute("UPDATE projects SET owner_user_id = %s WHERE id = %s;", (new_owner_id, project_id))
        conn.execute("""
            INSERT INTO project_members (project_id, user_id, role)
            VALUES (%s, %s, 'owner')
            ON CONFLICT (project_id, user_id) DO UPDATE SET role = 'owner';
        """, (project_id, new_owner_id))
        conn.execute("""
            UPDATE project_members SET role = 'editor' 
            WHERE project_id = %s AND user_id = %s;
        """, (project_id, old_owner_id))
        conn.commit()
    return get_project(project_id)


def set_project_archived(project_id: UUID, is_archived: bool) -> dict[str, Any] | None:
    """Toggle the ongoing/archived filter tag. Non-destructive — project stays fully accessible."""
    sql = "UPDATE projects SET is_archived = %s WHERE id = %s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, (is_archived, project_id)).fetchone()
        conn.commit()
    return row


def soft_delete_project(project_id: UUID) -> dict[str, Any] | None:
    """Hide project behind the trash view; room scans and documents are untouched."""
    sql = "UPDATE projects SET deleted_at = now() WHERE id = %s AND deleted_at IS NULL RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, (project_id,)).fetchone()
        conn.commit()
    return row


def restore_project(project_id: UUID) -> dict[str, Any] | None:
    """Undo a soft delete."""
    sql = "UPDATE projects SET deleted_at = NULL WHERE id = %s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, (project_id,)).fetchone()
        conn.commit()
    return row


def find_project_exclusive_documents(project_id: UUID) -> list[UUID]:
    """Documents tied only to this project (via project_documents or documents.project_id),
    not shared with any other project. These are what a hard delete removes."""
    sql = """
        SELECT d.id
        FROM documents d
        WHERE (
            d.project_id = %(project_id)s
            OR EXISTS (
                SELECT 1 FROM project_documents pd
                WHERE pd.document_id = d.id AND pd.project_id = %(project_id)s
            )
        )
        AND (d.project_id IS NULL OR d.project_id = %(project_id)s)
        AND NOT EXISTS (
            SELECT 1 FROM project_documents pd2
            WHERE pd2.document_id = d.id AND pd2.project_id != %(project_id)s
        );
    """
    with get_conn() as conn:
        rows = conn.execute(sql, {"project_id": project_id}).fetchall()
    return [row["id"] for row in rows]


def hard_delete_project(project_id: UUID) -> bool:
    """Permanently remove a project: cascades members/room-scan links (via FK), and also
    deletes documents (and their chunks) that are exclusive to this project. Shared
    documents and query_log rows detach (ON DELETE SET NULL) rather than get deleted."""
    exclusive_doc_ids = find_project_exclusive_documents(project_id)
    with get_conn() as conn:
        if exclusive_doc_ids:
            conn.execute("DELETE FROM documents WHERE id = ANY(%s);", (exclusive_doc_ids,))
        cur = conn.execute("DELETE FROM projects WHERE id = %s;", (project_id,))
        conn.commit()
    return cur.rowcount > 0


def set_active_project(user_id: UUID, project_id: UUID | None) -> None:
    """Persist the caller's single "active" project (or clear it with None)."""
    sql = "UPDATE users SET active_project_id = %s WHERE id = %s;"
    with get_conn() as conn:
        conn.execute(sql, (project_id, user_id))
        conn.commit()


# ════════════════════════════════════════════════
#  PROJECT MEMBERS (Sprint 9)
# ════════════════════════════════════════════════

def get_project_role(project_id: UUID, user_id: UUID) -> str | None:
    """Return role string or None if not a member."""
    sql = "SELECT role FROM project_members WHERE project_id = %s AND user_id = %s;"
    with get_conn() as conn:
        row = conn.execute(sql, (project_id, user_id)).fetchone()
    return row["role"] if row else None


def list_project_members(project_id: UUID) -> list[dict[str, Any]]:
    """Join with users table: returns user details and role."""
    sql = """
        SELECT u.id AS user_id, u.username, u.email, pm.role, pm.invited_at
        FROM project_members pm
        JOIN users u ON u.id = pm.user_id
        WHERE pm.project_id = %s
        ORDER BY pm.invited_at ASC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (project_id,)).fetchall()


def upsert_project_member(project_id: UUID, user_id: UUID, *, role: str) -> dict[str, Any]:
    """Add or update member role."""
    sql = """
        INSERT INTO project_members (project_id, user_id, role)
        VALUES (%(project_id)s, %(user_id)s, %(role)s::project_role)
        ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {"project_id": project_id, "user_id": user_id, "role": role}).fetchone()
        conn.commit()
    return row


def remove_project_member(project_id: UUID, user_id: UUID) -> bool:
    """Remove member. Cannot remove owner."""
    sql = """
        DELETE FROM project_members 
        WHERE project_id = %s AND user_id = %s AND role != 'owner';
    """
    with get_conn() as conn:
        cur = conn.execute(sql, (project_id, user_id))
        conn.commit()
    return cur.rowcount > 0


# ════════════════════════════════════════════════
#  PROJECT DOCUMENTS (Sprint 9)
# ════════════════════════════════════════════════

def share_document_to_project(project_id: UUID, document_id: UUID, added_by: UUID) -> dict[str, Any]:
    """Insert into project_documents (idempotent)."""
    sql = """
        INSERT INTO project_documents (project_id, document_id, added_by)
        VALUES (%(project_id)s, %(document_id)s, %(added_by)s)
        ON CONFLICT (project_id, document_id) DO NOTHING
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {
            "project_id": project_id,
            "document_id": document_id,
            "added_by": added_by,
        }).fetchone()
        conn.commit()
    return row or {"project_id": project_id, "document_id": document_id}


def list_project_documents(project_id: UUID) -> list[dict[str, Any]]:
    """JOIN documents — returns doc metadata for all docs shared into project."""
    sql = """
        SELECT d.*
        FROM project_documents pd
        JOIN documents d ON d.id = pd.document_id
        WHERE pd.project_id = %s
        ORDER BY d.municipality, d.doc_id;
    """
    with get_conn() as conn:
        return conn.execute(sql, (project_id,)).fetchall()


def unshare_document_from_project(project_id: UUID, document_id: UUID) -> bool:
    """DELETE from project_documents."""
    sql = "DELETE FROM project_documents WHERE project_id = %s AND document_id = %s;"
    with get_conn() as conn:
        cur = conn.execute(sql, (project_id, document_id))
        conn.commit()
    return cur.rowcount > 0


def get_user_query_history(user_id: UUID, project_id: UUID | None = None) -> list[dict[str, Any]]:
    """Fetch query log history for a specific user, sorted by newest first."""
    if project_id:
        sql = "SELECT id, query_text, municipality, top_k, answer_text, citations, model, latency_ms, created_at, project_id FROM query_log WHERE user_id = %s AND project_id = %s ORDER BY created_at DESC;"
        with get_conn() as conn:
            return conn.execute(sql, (user_id, project_id)).fetchall()
    else:
        sql = "SELECT id, query_text, municipality, top_k, answer_text, citations, model, latency_ms, created_at, project_id FROM query_log WHERE user_id = %s ORDER BY created_at DESC;"
        with get_conn() as conn:
            return conn.execute(sql, (user_id,)).fetchall()


def delete_user_query(user_id: UUID, query_id: UUID) -> bool:
    """Delete a specific query log entry belonging to the user."""
    sql = "DELETE FROM query_log WHERE id = %s AND user_id = %s;"
    with get_conn() as conn:
        cur = conn.execute(sql, (query_id, user_id))
        conn.commit()
    return cur.rowcount > 0


def get_all_users() -> list[dict[str, Any]]:
    """List all users in the system."""
    sql = "SELECT id, username, email, cognito_sub, role, is_active, created_at FROM users ORDER BY username ASC;"
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def delete_user_and_clean_up(user_id: UUID) -> bool:
    """Delete user account and safely reassign or clean up their owned projects."""
    with get_conn() as conn:
        # Find all projects owned by the user
        projects = conn.execute(
            "SELECT id FROM projects WHERE owner_user_id = %s AND deleted_at IS NULL;",
            (user_id,)
        ).fetchall()
        
        for p in projects:
            project_id = p["id"]
            # Find another member to transfer to
            candidate = conn.execute(
                """
                SELECT user_id, role FROM project_members 
                WHERE project_id = %s AND user_id != %s
                ORDER BY CASE WHEN role = 'editor' THEN 1 ELSE 2 END ASC, invited_at ASC
                LIMIT 1;
                """,
                (project_id, user_id)
            ).fetchone()
            
            if candidate:
                new_owner_id = candidate["user_id"]
                # Update project owner
                conn.execute(
                    "UPDATE projects SET owner_user_id = %s WHERE id = %s;",
                    (new_owner_id, project_id)
                )
                # Change candidate's role to owner
                conn.execute(
                    "UPDATE project_members SET role = 'owner' WHERE project_id = %s AND user_id = %s;",
                    (project_id, new_owner_id)
                )
            else:
                # No other members, delete project
                conn.execute("DELETE FROM projects WHERE id = %s;", (project_id,))
        
        # Delete user (cascades to project_members, set null on project_documents/documents/query_log)
        cur = conn.execute("DELETE FROM users WHERE id = %s;", (user_id,))
        conn.commit()
    return cur.rowcount > 0


# ════════════════════════════════════════════════
#  PROJECT ROOM SCANS (Sprint 14+ multi-scan)
# ════════════════════════════════════════════════


def list_project_room_scans(project_id: UUID) -> list[dict[str, Any]]:
    """List derived room/structure scan rows for a project."""
    sql = """
        SELECT *
        FROM project_room_scans
        WHERE project_id = %s
        ORDER BY captured_at DESC, room_label ASC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (project_id,)).fetchall()


def get_active_room_scan(project_id: UUID) -> dict[str, Any] | None:
    """Return the active room scan row for chat context."""
    sql = """
        SELECT urs.*
        FROM project_room_scan_links l
        JOIN user_room_scans urs ON urs.id = l.scan_id
        WHERE l.project_id = %s AND l.is_active = true AND urs.scan_type = 'room'
        LIMIT 1;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (project_id,)).fetchone()
        if row:
            return row
        legacy_sql = """
            SELECT *
            FROM project_room_scans
            WHERE project_id = %s AND scan_type = 'room' AND is_active = true
            LIMIT 1;
        """
        return conn.execute(legacy_sql, (project_id,)).fetchone()


def _room_summary_mirror_payload(
    *,
    room_label: str,
    section: str | None,
    captured_at: Any,
    derived: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build JSON-serializable room_summary mirror from an active room scan."""
    captured_value = (
        captured_at.isoformat()
        if hasattr(captured_at, "isoformat")
        else captured_at
    )
    return {
        "schema_version": "2.0",
        "room_label": room_label,
        "section": section,
        "captured_at": captured_value,
        "derived": derived or {},
    }


def upsert_project_room_scans(
    project_id: UUID,
    scans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Upsert structure and room scan summary rows (derived metrics only).

    When any room row sets is_active=true, clears other active room flags first.
    Mirrors active room derived to projects.room_summary for backward compatibility.
    """
    import json as _json

    if not scans:
        return list_project_room_scans(project_id)

    active_room_id: UUID | None = None
    active_summary: dict[str, Any] | None = None
    for scan in scans:
        if scan.get("scan_type") == "room" and scan.get("is_active"):
            active_room_id = scan["id"]
            active_summary = _room_summary_mirror_payload(
                room_label=scan.get("room_label", "room"),
                section=scan.get("section"),
                captured_at=scan.get("captured_at"),
                derived=scan.get("derived"),
            )
            break

    upsert_sql = """
        INSERT INTO project_room_scans (
            id, project_id, scan_type, parent_scan_id,
            room_label, section, captured_at, derived, is_active
        )
        VALUES (
            %(id)s, %(project_id)s, %(scan_type)s, %(parent_scan_id)s,
            %(room_label)s, %(section)s, %(captured_at)s,
            %(derived)s::jsonb, %(is_active)s
        )
        ON CONFLICT (id) DO UPDATE SET
            scan_type = EXCLUDED.scan_type,
            parent_scan_id = EXCLUDED.parent_scan_id,
            room_label = EXCLUDED.room_label,
            section = EXCLUDED.section,
            captured_at = EXCLUDED.captured_at,
            derived = EXCLUDED.derived,
            is_active = EXCLUDED.is_active,
            updated_at = now()
        RETURNING *;
    """

    with get_conn() as conn:
        if active_room_id is not None:
            conn.execute(
                """
                UPDATE project_room_scans
                SET is_active = false
                WHERE project_id = %s AND scan_type = 'room' AND id <> %s;
                """,
                (project_id, active_room_id),
            )
        for scan in scans:
            conn.execute(
                upsert_sql,
                {
                    "id": scan["id"],
                    "project_id": project_id,
                    "scan_type": scan["scan_type"],
                    "parent_scan_id": scan.get("parent_scan_id"),
                    "room_label": scan["room_label"],
                    "section": scan.get("section"),
                    "captured_at": scan["captured_at"],
                    "derived": _json.dumps(scan.get("derived") or {}),
                    "is_active": bool(scan.get("is_active")),
                },
            )
        if active_summary is not None:
            conn.execute(
                """
                UPDATE projects
                SET room_summary = %(room_summary)s::jsonb
                WHERE id = %(project_id)s;
                """,
                {
                    "project_id": project_id,
                    "room_summary": _json.dumps(active_summary),
                },
            )
        conn.commit()
    return list_project_room_scans(project_id)


def set_active_room_scan(project_id: UUID, scan_id: UUID) -> dict[str, Any] | None:
    """Mark one room scan active and mirror derived summary to projects.room_summary."""
    import json as _json

    linked = set_active_linked_room_scan(project_id, scan_id)
    if linked:
        return linked

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM project_room_scans
            WHERE id = %s AND project_id = %s AND scan_type = 'room';
            """,
            (scan_id, project_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            """
            UPDATE project_room_scans
            SET is_active = false
            WHERE project_id = %s AND scan_type = 'room';
            """,
            (project_id,),
        )
        updated = conn.execute(
            """
            UPDATE project_room_scans
            SET is_active = true
            WHERE id = %s
            RETURNING *;
            """,
            (scan_id,),
        ).fetchone()
        summary = _room_summary_mirror_payload(
            room_label=updated["room_label"],
            section=updated.get("section"),
            captured_at=updated["captured_at"],
            derived=updated.get("derived"),
        )
        conn.execute(
            """
            UPDATE projects
            SET room_summary = %(room_summary)s::jsonb
            WHERE id = %(project_id)s;
            """,
            {"project_id": project_id, "room_summary": _json.dumps(summary)},
        )
        conn.commit()
    return updated


# ════════════════════════════════════════════════
#  USER ROOM SCAN LIBRARY (Sprint 15)
# ════════════════════════════════════════════════


def list_user_room_scans(user_id: UUID) -> list[dict[str, Any]]:
    """List all scans in a user's personal library."""
    sql = """
        SELECT *
        FROM user_room_scans
        WHERE user_id = %s
        ORDER BY captured_at DESC, room_label ASC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (user_id,)).fetchall()


def upsert_user_room_scans(
    user_id: UUID,
    scans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Upsert derived summaries into the user's scan library."""
    import json as _json

    if not scans:
        return list_user_room_scans(user_id)

    upsert_sql = """
        INSERT INTO user_room_scans (
            id, user_id, scan_type, parent_scan_id, room_label, section,
            structure_label, captured_at, derived
        )
        VALUES (
            %(id)s, %(user_id)s, %(scan_type)s, %(parent_scan_id)s,
            %(room_label)s, %(section)s, %(structure_label)s,
            %(captured_at)s, %(derived)s::jsonb
        )
        ON CONFLICT (id) DO UPDATE SET
            scan_type = EXCLUDED.scan_type,
            parent_scan_id = EXCLUDED.parent_scan_id,
            room_label = EXCLUDED.room_label,
            section = EXCLUDED.section,
            structure_label = EXCLUDED.structure_label,
            captured_at = EXCLUDED.captured_at,
            derived = EXCLUDED.derived,
            updated_at = now()
        RETURNING *;
    """
    with get_conn() as conn:
        for scan in scans:
            conn.execute(
                upsert_sql,
                {
                    "id": scan["id"],
                    "user_id": user_id,
                    "scan_type": scan["scan_type"],
                    "parent_scan_id": scan.get("parent_scan_id"),
                    "room_label": scan["room_label"],
                    "section": scan.get("section"),
                    "structure_label": scan.get("structure_label"),
                    "captured_at": scan["captured_at"],
                    "derived": _json.dumps(scan.get("derived") or {}),
                },
            )
        conn.commit()
    return list_user_room_scans(user_id)


def list_linked_project_room_scans(project_id: UUID) -> list[dict[str, Any]]:
    """List library scans linked to a project."""
    sql = """
        SELECT
            urs.*,
            l.project_id,
            l.is_active,
            l.linked_at
        FROM project_room_scan_links l
        JOIN user_room_scans urs ON urs.id = l.scan_id
        WHERE l.project_id = %s
        ORDER BY urs.captured_at DESC, urs.room_label ASC;
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (project_id,)).fetchall()
    if rows:
        return rows
    return list_project_room_scans(project_id)


def link_scans_to_project(
    project_id: UUID,
    user_id: UUID,
    scan_ids: list[UUID],
    *,
    active_scan_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Attach library scans to a project; optionally set active room."""
    import json as _json

    owned = list_user_room_scans(user_id)
    owned_ids = {row["id"] for row in owned}
    for scan_id in scan_ids:
        if scan_id not in owned_ids:
            raise ValueError(f"Scan {scan_id} not found in user library.")

    with get_conn() as conn:
        for scan_id in scan_ids:
            conn.execute(
                """
                INSERT INTO project_room_scan_links (project_id, scan_id, is_active)
                VALUES (%s, %s, false)
                ON CONFLICT (project_id, scan_id) DO NOTHING;
                """,
                (project_id, scan_id),
            )
        if active_scan_id is not None:
            conn.execute(
                "UPDATE project_room_scan_links SET is_active = false WHERE project_id = %s;",
                (project_id,),
            )
            conn.execute(
                """
                UPDATE project_room_scan_links
                SET is_active = true
                WHERE project_id = %s AND scan_id = %s;
                """,
                (project_id, active_scan_id),
            )
            row = conn.execute(
                """
                SELECT urs.*
                FROM project_room_scan_links l
                JOIN user_room_scans urs ON urs.id = l.scan_id
                WHERE l.project_id = %s AND l.scan_id = %s AND urs.scan_type = 'room';
                """,
                (project_id, active_scan_id),
            ).fetchone()
            if row:
                summary = _room_summary_mirror_payload(
                    room_label=row["room_label"],
                    section=row.get("section"),
                    captured_at=row["captured_at"],
                    derived=row.get("derived"),
                )
                conn.execute(
                    """
                    UPDATE projects SET room_summary = %(room_summary)s::jsonb
                    WHERE id = %(project_id)s;
                    """,
                    {"project_id": project_id, "room_summary": _json.dumps(summary)},
                )
        conn.commit()
    return list_linked_project_room_scans(project_id)


def unlink_scan_from_project(project_id: UUID, scan_id: UUID) -> bool:
    """Remove a scan link from a project (library entry remains)."""
    with get_conn() as conn:
        cur = conn.execute(
            """
            DELETE FROM project_room_scan_links
            WHERE project_id = %s AND scan_id = %s;
            """,
            (project_id, scan_id),
        )
        conn.commit()
    return cur.rowcount > 0


def set_active_linked_room_scan(project_id: UUID, scan_id: UUID) -> dict[str, Any] | None:
    """Mark a linked room scan active for project chat context."""
    import json as _json

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT urs.*
            FROM project_room_scan_links l
            JOIN user_room_scans urs ON urs.id = l.scan_id
            WHERE l.project_id = %s AND l.scan_id = %s AND urs.scan_type = 'room';
            """,
            (project_id, scan_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE project_room_scan_links SET is_active = false WHERE project_id = %s;",
            (project_id,),
        )
        conn.execute(
            """
            UPDATE project_room_scan_links
            SET is_active = true
            WHERE project_id = %s AND scan_id = %s;
            """,
            (project_id, scan_id),
        )
        summary = _room_summary_mirror_payload(
            room_label=row["room_label"],
            section=row.get("section"),
            captured_at=row["captured_at"],
            derived=row.get("derived"),
        )
        conn.execute(
            """
            UPDATE projects SET room_summary = %(room_summary)s::jsonb WHERE id = %(project_id)s;
            """,
            {"project_id": project_id, "room_summary": _json.dumps(summary)},
        )
        conn.commit()
    return row


def insert_design_intent_usage(
    *,
    user_id: UUID,
    project_id: UUID | None,
    room_scan_id: UUID,
    input_tokens: int,
    output_tokens: int,
    model: str,
) -> dict[str, Any]:
    """Log one design-intent LLM call for token accounting."""
    sql = """
        INSERT INTO design_intent_usage (
            user_id, project_id, room_scan_id,
            input_tokens, output_tokens, model
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (user_id, project_id, room_scan_id, input_tokens, output_tokens, model),
        ).fetchone()
        conn.commit()
    return row


def sum_design_intent_tokens(user_id: UUID, *, since: datetime) -> int:
    """Sum input + output tokens for a user since a timestamp."""
    sql = """
        SELECT COALESCE(SUM(input_tokens + output_tokens), 0) AS total
        FROM design_intent_usage
        WHERE user_id = %s AND created_at >= %s;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (user_id, since)).fetchone()
    return int(row["total"]) if row else 0

