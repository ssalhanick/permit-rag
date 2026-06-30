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
from datetime import date
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

def create_project(
    *,
    name: str,
    owner_user_id: UUID,
    description: str | None = None,
    municipality: str | None = None,
) -> dict[str, Any]:
    """Create a project and auto-enroll the owner in one transaction."""
    sql_project = """
        INSERT INTO projects (name, owner_user_id, description, municipality)
        VALUES (%(name)s, %(owner_user_id)s, %(description)s, %(municipality)s)
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
        }).fetchone()
        conn.execute(sql_member, {"project_id": row["id"], "user_id": owner_user_id})
        conn.commit()
    log.info("Created project: %s (owner=%s)", name, owner_user_id)
    return row


def get_project(project_id: UUID) -> dict[str, Any] | None:
    """Fetch active project by UUID."""
    sql = "SELECT * FROM projects WHERE id = %s AND is_active = true;"
    with get_conn() as conn:
        return conn.execute(sql, (project_id,)).fetchone()


def list_projects_for_user(user_id: UUID) -> list[dict[str, Any]]:
    """All active projects where user is a member (any role)."""
    sql = """
        SELECT p.*
        FROM projects p
        JOIN project_members pm ON pm.project_id = p.id
        WHERE pm.user_id = %s AND p.is_active = true
        ORDER BY p.created_at DESC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (user_id,)).fetchall()


def update_project(
    project_id: UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    municipality: str | None = None,
) -> dict[str, Any] | None:
    """Update mutable project fields."""
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


def archive_project(project_id: UUID) -> dict[str, Any] | None:
    """Soft-delete: set is_active=False."""
    sql = "UPDATE projects SET is_active = false WHERE id = %s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, (project_id,)).fetchone()
        conn.commit()
    return row


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
            "SELECT id FROM projects WHERE owner_user_id = %s AND is_active = true;",
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

