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


def get_jurisdiction_chain(jurisdiction_id: str) -> list[str]:
    """
    Walk `jurisdictions.parent_id` up from jurisdiction_id to its root.

    e.g. "dallas" -> ["dallas", "dallas-county", "texas", "federal"]. Depth is
    bounded at 10 to guard against a cyclic parent_id; the table has ~15 rows
    today so this is a single, sub-millisecond round trip.

    Returns just [jurisdiction_id] if it has no row (unknown id) — callers that
    filter retrieval by this chain should still see at least an exact-match
    filter rather than silently degrading to "no filter at all".
    """
    sql = """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, 1 AS depth FROM jurisdictions WHERE id = %(start)s
            UNION ALL
            SELECT j.id, j.parent_id, chain.depth + 1
            FROM jurisdictions j JOIN chain ON j.id = chain.parent_id
            WHERE chain.depth < 10
        )
        SELECT id FROM chain ORDER BY depth;
    """
    with get_conn() as conn:
        rows = conn.execute(sql, {"start": jurisdiction_id}).fetchall()
    return [r["id"] for r in rows] if rows else [jurisdiction_id]


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
    content_class: str = "authority",  # migration 031: 'authority' | 'how_to'
    overlay_id: UUID | None = None,  # migration 038: linked overlay petition, if any
    visibility: str = "team",  # migration 040: 'private' | 'team' -- tier-3 only
) -> dict[str, Any]:
    """
    Insert a document row. Returns the full row as a dict.

    Uses ON CONFLICT to update metadata if the doc_id already exists,
    which supports re-harvesting without duplicating rows.

    ``content_class`` defaults to ``"authority"`` (permit corpus). The Media
    Curator transcript ingest passes ``"how_to"`` so those docs are segregated
    out of compliance retrieval (migration 031).
    """
    sql = """
        INSERT INTO documents (
            doc_id, source_url, municipality, authority_level,
            doc_type, subject_tags, effective_date, document_status,
            is_current, retrieval_weight, review_due,
            checksum_sha256, source_etag, local_path, source_tier,
            project_id, uploaded_by, content_class, overlay_id, visibility
        ) VALUES (
            %(doc_id)s, %(source_url)s, %(municipality)s,
            %(authority_level)s::authority_level,
            %(doc_type)s::doc_type,
            %(subject_tags)s,
            %(effective_date)s, %(document_status)s::document_status,
            %(is_current)s, %(retrieval_weight)s, %(review_due)s,
            %(checksum_sha256)s, %(source_etag)s, %(local_path)s,
            %(source_tier)s, %(project_id)s, %(uploaded_by)s, %(content_class)s,
            %(overlay_id)s, %(visibility)s::document_visibility
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
            uploaded_by      = EXCLUDED.uploaded_by,
            content_class    = EXCLUDED.content_class,
            overlay_id       = EXCLUDED.overlay_id,
            visibility       = EXCLUDED.visibility
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
        "content_class": content_class,
        "overlay_id": overlay_id,
        "visibility": visibility,
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
    content_class: str | None = "authority",
) -> list[dict[str, Any]]:
    """
    List documents with optional municipality/status/authority/doc_type filters.

    ``content_class`` defaults to ``"authority"`` so the compliance corpus views
    exclude how-to video transcripts (migration 031). Pass ``None`` to list every
    class. Returns all columns, ordered by municipality then doc_id.
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
    if content_class:
        clauses.append("content_class = %(content_class)s")
        params["content_class"] = content_class

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM documents {where} ORDER BY municipality, doc_id;"

    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def list_covered_municipalities() -> list[dict[str, Any]]:
    """City-level jurisdictions with >=1 active, current, authority-class document.

    Joined against `jurisdictions` for a display `name` (falls back to the raw
    id if a document's municipality has no jurisdictions row yet). Restricted
    to `level = 'city'` — county/state/federal municipality values exist in
    `documents` too, but "which city is your project in" listings shouldn't
    include them. Used by rag.coverage to tell "real coverage" apart from
    jurisdictions that are seeded/advertised but have no retrievable content.
    """
    sql = """
        SELECT DISTINCT d.municipality AS id, COALESCE(j.name, d.municipality) AS name
        FROM documents d
        LEFT JOIN jurisdictions j ON j.id = d.municipality
        WHERE d.document_status = 'active' AND d.is_current = true
          AND d.content_class = 'authority'
          AND (j.id IS NULL OR j.level = 'city')
        ORDER BY name;
    """
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def match_overlay_chunks(
    query_embedding: list[float],
    *,
    latitude: float,
    longitude: float,
    top_k: int = 5,
    min_similarity: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Dense search over documents linked to an APPROVED overlay whose geometry
    contains (latitude, longitude) — migration 038.

    This is what makes a petitioned historic/conservation-district or HOA
    document surface for ANY project physically inside its tight boundary, not
    just the project that originally petitioned it.
    """
    sql = """
        SELECT
            c.id, c.document_id, d.doc_id, c.content, c.chunk_index,
            d.municipality, d.authority_level, d.doc_type, d.document_status,
            c.status AS chunk_status, d.source_tier, d.ingested_at,
            d.retrieval_weight,
            1 - (c.embedding <=> %(query_embedding)s::vector) AS similarity
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN overlays o ON o.id = d.overlay_id
        WHERE o.status = 'approved'
          AND o.geom IS NOT NULL
          AND ST_Contains(o.geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326))
          AND d.document_status = 'active' AND d.is_current = true
          AND c.status = 'active'
        ORDER BY c.embedding <=> %(query_embedding)s::vector
        LIMIT %(top_k)s;
    """
    params = {
        "query_embedding": str(query_embedding),
        "lat": latitude,
        "lng": longitude,
        "top_k": top_k,
    }
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    if min_similarity > 0.0:
        rows = [r for r in rows if r["similarity"] >= min_similarity]
    return rows


# ════════════════════════════════════════════════
#  OVERLAYS (migration 038) — historic/conservation/HOA petitions
# ════════════════════════════════════════════════


def list_overlays_containing_point(latitude: float, longitude: float) -> list[dict[str, Any]]:
    """Approved overlays (historic/conservation district, HOA) whose boundary
    contains (latitude, longitude) — metadata only, no chunk search.

    Document-upload plan, Type 3 coverage-surfacing addition: this is what lets
    GET /projects/{project_id}/coverage report "you're in the Swiss Ave
    Historic District" alongside the municipality-level status, using the same
    ST_Contains pattern as match_overlay_chunks.
    """
    sql = """
        SELECT id, name, overlay_type, jurisdiction_id, status,
               petitioning_project_id, approved_by, approved_at, notes, created_at
        FROM overlays
        WHERE status = 'approved'
          AND geom IS NOT NULL
          AND ST_Contains(geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326))
        ORDER BY approved_at ASC;
    """
    with get_conn() as conn:
        return conn.execute(sql, {"lat": latitude, "lng": longitude}).fetchall()


def create_overlay_petition(
    *,
    name: str,
    overlay_type: str,
    jurisdiction_id: str | None,
    petitioned_by: UUID | None,
    petitioning_project_id: UUID,
    latitude: float,
    longitude: float,
    buffer_meters: float = 200.0,
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Create a 'petitioned' overlay with a coarse default geometry.

    The default geometry is a circular buffer (in real meters, via a
    geography cast) around the petitioning project's point — a v1 petitioner
    isn't expected to hand-draw a precise polygon. Staff can replace it with a
    refined boundary at/before approval (see approve_overlay).
    """
    sql = """
        INSERT INTO overlays (
            name, overlay_type, jurisdiction_id, geom, status,
            petitioned_by, petitioning_project_id, notes
        ) VALUES (
            %(name)s, %(overlay_type)s::overlay_type, %(jurisdiction_id)s,
            ST_Multi(ST_Buffer(
                ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography,
                %(buffer_meters)s
            )::geometry),
            'petitioned', %(petitioned_by)s, %(petitioning_project_id)s, %(notes)s
        )
        RETURNING *;
    """
    params = {
        "name": name,
        "overlay_type": overlay_type,
        "jurisdiction_id": jurisdiction_id,
        "lat": latitude,
        "lng": longitude,
        "buffer_meters": buffer_meters,
        "petitioned_by": petitioned_by,
        "petitioning_project_id": petitioning_project_id,
        "notes": notes,
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    log.info("Created overlay petition: %s (%s) for project=%s", row["id"], name, petitioning_project_id)
    return row


def get_overlay(overlay_id: UUID) -> dict[str, Any] | None:
    """Fetch a single overlay row by id."""
    sql = "SELECT * FROM overlays WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (overlay_id,)).fetchone()


def list_pending_overlay_petitions() -> list[dict[str, Any]]:
    """List overlays awaiting staff review, oldest first."""
    sql = "SELECT * FROM overlays WHERE status = 'petitioned' ORDER BY created_at ASC;"
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def approve_overlay(
    overlay_id: UUID,
    *,
    approved_by: UUID | None,
    geojson_polygon: str | None = None,
) -> dict[str, Any] | None:
    """
    Approve a petitioned overlay, making its documents retrievable project-wide.

    If ``geojson_polygon`` (a GeoJSON geometry as a JSON string) is given, it
    replaces the petitioner's default buffer with a refined "tight boundary"
    before approving. Otherwise the existing geometry (the default buffer, if
    never refined) stands as the approved boundary.
    """
    if geojson_polygon:
        sql = """
            UPDATE overlays
            SET status = 'approved', approved_by = %(approved_by)s, approved_at = now(),
                geom = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326))
            WHERE id = %(overlay_id)s
            RETURNING *;
        """
        params = {"overlay_id": overlay_id, "approved_by": approved_by, "geojson": geojson_polygon}
    else:
        sql = """
            UPDATE overlays
            SET status = 'approved', approved_by = %(approved_by)s, approved_at = now()
            WHERE id = %(overlay_id)s
            RETURNING *;
        """
        params = {"overlay_id": overlay_id, "approved_by": approved_by}
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    if row:
        log.info("Approved overlay %s by %s", overlay_id, approved_by)
    return row


def reject_overlay(overlay_id: UUID, *, approved_by: UUID | None) -> dict[str, Any] | None:
    """Reject a petitioned overlay. Reuses approved_by/approved_at as the reviewer/review-time fields."""
    sql = """
        UPDATE overlays
        SET status = 'rejected', approved_by = %(approved_by)s, approved_at = now()
        WHERE id = %(overlay_id)s
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {"overlay_id": overlay_id, "approved_by": approved_by}).fetchone()
        conn.commit()
    return row


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


def update_document_metadata_fields(
    doc_id: str,
    *,
    effective_date: date | None = None,
    doc_type: str | None = None,
    authority_level: str | None = None,
    subject_tags: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Correct a document's retrieval-driving metadata by doc_id.

    These four fields — effective_date, doc_type, authority_level, subject_tags —
    are exactly what the reranker and retrieval filters read, and are the fields
    the Corpus Metadata Validator (agent #13) proposes fixes for. They are kept
    out of ``update_document_admin_fields`` (which owns governance/lifecycle
    fields) so the two write paths stay separate. Per AGENTS.md the validator
    never calls this directly — it flows through ``ingestion/governance.py``,
    which is the only writer of corrected corpus metadata.

    Only non-None fields are written; passing all None re-reads the row.
    """
    assignments: list[str] = []
    params: dict[str, Any] = {"doc_id": doc_id}

    if effective_date is not None:
        assignments.append("effective_date = %(effective_date)s")
        params["effective_date"] = effective_date
    if doc_type is not None:
        assignments.append("doc_type = %(doc_type)s::doc_type")
        params["doc_type"] = doc_type
    if authority_level is not None:
        assignments.append("authority_level = %(authority_level)s::authority_level")
        params["authority_level"] = authority_level
    if subject_tags is not None:
        assignments.append("subject_tags = %(subject_tags)s")
        params["subject_tags"] = subject_tags

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
    municipalities: list[str] | None = None,
    min_similarity: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Dense vector similarity search via the match_chunks() SQL function.

    Calls the pgvector cosine-distance search defined in db/schema.sql. As of
    migration 031 the SQL function is scoped to ``content_class = 'authority'`` —
    how-to video transcripts are excluded from compliance retrieval **in SQL**.
    As of migration 037, ``filter_municipality`` is a jurisdiction chain
    (``text[]``) rather than a single string, so a city-scoped query also
    matches its county/state/federal documents instead of excluding them.
    Returns up to *top_k* chunks ordered by source_tier ASC then descending
    similarity.

    Args:
        query_embedding: 768-dim float vector (nomic-embed-text query).
        top_k: Maximum number of chunks to return.
        municipalities: Optional jurisdiction chain to filter by, e.g.
            ``["dallas", "dallas-county", "texas", "federal"]``. Pass None for
            no filter.
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
        "filter_municipality": municipalities,
    }
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    # Apply client-side similarity floor
    if min_similarity > 0.0:
        rows = [r for r in rows if r["similarity"] >= min_similarity]

    log.info(
        "match_chunks: %d results (top_k=%d, municipalities=%s)",
        len(rows), top_k, municipalities,
    )
    return rows


def match_how_to_chunks(
    query_embedding: list[float],
    *,
    top_k: int = 5,
    municipality: str | None = None,
    min_similarity: float = 0.0,
) -> list[dict[str, Any]]:
    """
    Dense search over the how-to transcript class only (migration 031).

    The DIY how-to retrieval: returns ``content_class = 'how_to'`` chunks (video
    transcripts) via the ``match_how_to_chunks()`` SQL function. Kept entirely
    separate from :func:`match_chunks` so how-to content can never ground or cite
    a compliance answer. Same row shape as ``match_chunks``.
    """
    sql = """
        SELECT * FROM match_how_to_chunks(
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

    if min_similarity > 0.0:
        rows = [r for r in rows if r["similarity"] >= min_similarity]

    log.info("match_how_to_chunks: %d results (top_k=%d)", len(rows), top_k)
    return rows


def match_project_chunks(
    query_embedding: list[float],
    *,
    project_id: UUID,
    top_k: int = 5,
    min_similarity: float = 0.0,
    requesting_user_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """
    Vector search limited to tier 2/3 documents for a project.

    Includes docs with documents.project_id or linked via project_documents.

    Tier-3 (project-specific, migration 040) rows are additionally gated by
    ``visibility``: 'team' docs are always included, 'private' docs only when
    ``requesting_user_id`` matches ``uploaded_by``. Tier-2 rows are unaffected
    (visibility is only meaningful for tier-3). ``requesting_user_id=None``
    (an unauthenticated or system caller) sees 'team' docs only -- ``uploaded_by
    = NULL`` never matches a real row under SQL's NULL semantics, so no extra
    branching is needed to keep private docs hidden by default.

    Args:
        query_embedding: 768-dim query vector.
        project_id: Project scope UUID.
        top_k: Max results.
        min_similarity: Cosine similarity floor.
        requesting_user_id: The querying user, for the tier-3 visibility filter.

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
        WHERE d.document_status = 'active'
          AND c.status = 'active'
          AND c.embedding IS NOT NULL
          AND (d.project_id = %(project_id)s OR pd.project_id = %(project_id)s)
          AND (
                d.source_tier = 2
             OR (d.source_tier = 3 AND (
                    d.visibility = 'team' OR d.uploaded_by = %(requesting_user_id)s
                 ))
          )
        ORDER BY d.source_tier ASC, similarity DESC
        LIMIT %(match_count)s;
    """
    params = {
        "query_embedding": str(query_embedding),
        "project_id": project_id,
        "match_count": top_k,
        "requesting_user_id": requesting_user_id,
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
    municipalities: list[str] | None,
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
          AND (%(municipalities)s::text[] IS NULL OR d.municipality = ANY(%(municipalities)s::text[]))
        ORDER BY similarity DESC, c.chunk_index ASC
        LIMIT %(top_k)s;
    """
    params = {
        "query_text": query_text,
        "municipalities": municipalities,
        "top_k": top_k,
    }
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def search_chunks_bm25(
    query_text: str,
    *,
    top_k: int = 5,
    municipalities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Lexical retrieval using chunks.search_vector with BM25-style ranking.

    Returns the same row shape as match_chunks(), where similarity maps to
    ts_rank_cd score for compatibility with downstream ranking. `municipalities`
    is a jurisdiction chain (see match_chunks) rather than a single string, so
    hybrid retrieval stays consistent with the dense path once
    RETRIEVAL_HYBRID_ENABLED is turned on.
    """
    try:
        rows = _search_chunks_with_tsquery(
            query_text,
            top_k=top_k,
            municipalities=municipalities,
            tsquery_func="websearch_to_tsquery",
        )
    except psycopg.Error:
        rows = _search_chunks_with_tsquery(
            query_text,
            top_k=top_k,
            municipalities=municipalities,
            tsquery_func="plainto_tsquery",
        )
    log.info(
        "search_chunks_bm25: %d results (top_k=%d, municipalities=%s)",
        len(rows), top_k, municipalities,
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

    stage:  'download' | 'extraction' | 'chunking' | 'embedding' | 'metadata'
    result: 'pass' | 'fail' | 'skip' | 'needs_ocr' | 'needs_review'
    detail: arbitrary JSON payload with stage-specific metrics
            ('metadata' + 'needs_review' added in migration 028)
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
    session_id: UUID | None = None,
) -> dict[str, Any]:
    """Log a RAG query for auditing and evaluation."""
    import json as _json

    sql = """
        INSERT INTO query_log
            (query_text, municipality, top_k, chunk_ids,
             answer_text, citations, model, latency_ms, user_id, project_id,
             session_id)
        VALUES
            (%(query_text)s, %(municipality)s, %(top_k)s,
             %(chunk_ids)s, %(answer_text)s,
             %(citations)s::jsonb, %(model)s, %(latency_ms)s,
             %(user_id)s, %(project_id)s, %(session_id)s)
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
        "session_id": session_id,
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


def sync_user_role(user_id: UUID, role: str) -> None:
    """Mirror a Cognito-derived global role onto the users row.

    Called on every authenticated request so demotions (leaving the Cognito
    admin/superadmin group) take effect on the next login without a manual
    SQL edit. No-ops when the role already matches to avoid a write per request.
    """
    sql = """
        UPDATE users
        SET role = %(role)s, role_synced_at = now()
        WHERE id = %(user_id)s AND role != %(role)s;
    """
    with get_conn() as conn:
        conn.execute(sql, {"user_id": user_id, "role": role})
        conn.commit()


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
    project_notes: str | None = None,
) -> dict[str, Any]:
    """Create a project and auto-enroll the owner in one transaction."""
    import json as _json

    sql_project = """
        INSERT INTO projects (
            name, owner_user_id, description, municipality,
            address, latitude, longitude, historic_district, conservation_district,
            spaces, work_types, materials, recommended_permits, budget, persona, custom_system_prompt,
            project_notes
        )
        VALUES (
            %(name)s, %(owner_user_id)s, %(description)s, %(municipality)s,
            %(address)s, %(latitude)s, %(longitude)s, %(historic_district)s, %(conservation_district)s,
            %(spaces)s, %(work_types)s, %(materials)s, %(recommended_permits)s, %(budget)s, %(persona)s, %(custom_system_prompt)s,
            %(project_notes)s
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
            "project_notes": project_notes,
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


def list_all_projects(
    *,
    status: str | None = None,
    search: str | None = None,
    has_room_scans: bool | None = None,
) -> list[dict[str, Any]]:
    """All projects regardless of membership — staff (admin/superadmin) read bypass."""
    where = []
    params: dict[str, Any] = {}

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

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    sql = f"""
        SELECT p.*
        FROM projects p
        {where_clause}
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
    experience: str | None = None,
    project_notes: str | None = None,
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
    if experience is not None:
        assignments.append("experience = %(experience)s")
        params["experience"] = experience
    if project_notes is not None:
        assignments.append("project_notes = %(project_notes)s")
        params["project_notes"] = project_notes
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


def set_project_marketplace_status(project_id: UUID, status: str) -> dict[str, Any] | None:
    """Open/close a project for contractor bidding. Opening stamps listed_at once."""
    if status == "open":
        sql = """
            UPDATE projects
            SET marketplace_status = %s, listed_at = COALESCE(listed_at, now())
            WHERE id = %s
            RETURNING *;
        """
    else:
        sql = "UPDATE projects SET marketplace_status = %s WHERE id = %s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, (status, project_id)).fetchone()
        conn.commit()
    return row


def list_marketplace_projects(
    *,
    trade: str | None = None,
    municipality: str | None = None,
) -> list[dict[str, Any]]:
    """Open listings for the contractor browse/filter view, newest-listed first."""
    where = ["marketplace_status = 'open'", "deleted_at IS NULL"]
    params: dict[str, Any] = {}
    if trade:
        where.append("work_types @> %(trade)s::jsonb")
        import json as _json

        params["trade"] = _json.dumps([trade])
    if municipality:
        where.append("municipality = %(municipality)s")
        params["municipality"] = municipality
    sql = f"""
        SELECT * FROM projects
        WHERE {' AND '.join(where)}
        ORDER BY listed_at DESC NULLS LAST;
    """
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


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


def insert_project_delete_audit_log(
    *,
    project_id: UUID,
    project_name: str,
    owner_user_id: UUID | None,
    actor_user_id: UUID,
    actor_username: str,
    actor_role: str,
    action: str,
) -> dict[str, Any]:
    """Record a soft-delete / restore / hard-delete event for a project.

    No FK on project_id -- hard_delete_project removes the projects row before
    this is called, so project_name is a snapshot for a still-readable log.
    """
    sql = """
        INSERT INTO project_delete_audit_log (
            project_id, project_name, owner_user_id, actor_user_id,
            actor_username, actor_role, action
        ) VALUES (
            %(project_id)s, %(project_name)s, %(owner_user_id)s, %(actor_user_id)s,
            %(actor_username)s, %(actor_role)s, %(action)s
        )
        RETURNING *;
    """
    params = {
        "project_id": project_id,
        "project_name": project_name,
        "owner_user_id": owner_user_id,
        "actor_user_id": actor_user_id,
        "actor_username": actor_username,
        "actor_role": actor_role,
        "action": action,
    }
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


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


def delete_project_document(document_id: UUID) -> bool:
    """Hard-delete a tier-3 project document: its chunks, then the row itself,
    in one transaction. Returns False (no-op) if the id isn't a tier-3 document.

    Deliberately not a blanket ON DELETE CASCADE off uploaded_by -- that FK is
    shared with tier-1/tier-2 corpus documents, which must survive user
    deletion. The ``source_tier = 3`` guard on the DELETE itself means this is
    safe to call with any document_id: it can only ever remove a project doc.
    ``project_documents`` cleans itself up via its own ON DELETE CASCADE
    (migration 011) once the documents row is gone.
    """
    sql_chunks = "DELETE FROM chunks WHERE document_id = %s;"
    sql_document = "DELETE FROM documents WHERE id = %s AND source_tier = 3;"
    with get_conn() as conn:
        conn.execute(sql_chunks, (document_id,))
        cur = conn.execute(sql_document, (document_id,))
        conn.commit()
    deleted = cur.rowcount > 0
    if deleted:
        log.info("Deleted project document %s (chunks + row, one transaction)", document_id)
    return deleted


def get_pending_documents() -> list[dict[str, Any]]:
    """List tier-2 ordinance petitions awaiting staff review (migration 041 /
    Type 1). Oldest first, so the admin queue works through the backlog in order."""
    sql = """
        SELECT * FROM documents
        WHERE source_tier = 2 AND document_status = 'draft'
        ORDER BY ingested_at ASC;
    """
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def approve_pending_document(doc_id: str) -> dict[str, Any] | None:
    """Promote a tier-2 ordinance petition into the shared tier-1 corpus.

    Scoped to source_tier = 2 in the WHERE clause so this can't be pointed at
    an already-tier-1 (or tier-3) document by mistake. Returns None if doc_id
    doesn't exist or isn't a pending tier-2 document.
    """
    sql = """
        UPDATE documents
        SET source_tier = 1, document_status = 'active'
        WHERE doc_id = %s AND source_tier = 2
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (doc_id,)).fetchone()
        conn.commit()
    if row:
        log.info("Approved pending document: %s (tier 2 -> 1, active)", doc_id)
    return row


def reject_pending_document(doc_id: str) -> bool:
    """Reject a tier-2 ordinance petition: delete its chunks and the document
    row, in one transaction. documents.document_status has no 'rejected'
    value (unlike overlays' status enum) — deletion is the terminal state
    here rather than adding an enum value for one workflow. Scoped to
    source_tier = 2 so this can't delete an already-approved (tier-1) or
    project (tier-3) document.
    """
    sql_lookup = "SELECT id FROM documents WHERE doc_id = %s AND source_tier = 2;"
    sql_chunks = "DELETE FROM chunks WHERE document_id = %s;"
    sql_document = "DELETE FROM documents WHERE doc_id = %s AND source_tier = 2;"
    with get_conn() as conn:
        row = conn.execute(sql_lookup, (doc_id,)).fetchone()
        if row is None:
            return False
        conn.execute(sql_chunks, (row["id"],))
        cur = conn.execute(sql_document, (doc_id,))
        conn.commit()
    rejected = cur.rowcount > 0
    if rejected:
        log.info("Rejected pending document: %s (chunks + row deleted)", doc_id)
    return rejected


def set_user_verified_contributor(user_id: UUID, is_verified_contributor: bool) -> dict[str, Any] | None:
    """Admin-settable trust flag (migration 041) gating Type-1 ordinance-
    petition auto-approval. Returns None if the user doesn't exist or isn't active."""
    sql = """
        UPDATE users SET is_verified_contributor = %(value)s
        WHERE id = %(user_id)s AND is_active = true
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {"value": is_verified_contributor, "user_id": user_id}).fetchone()
        conn.commit()
    return row


def get_user_query_history(user_id: UUID, project_id: UUID | None = None) -> list[dict[str, Any]]:
    """Fetch query log history for a specific user, sorted by newest first."""
    if project_id:
        sql = "SELECT id, query_text, municipality, top_k, answer_text, citations, model, latency_ms, created_at, project_id, session_id FROM query_log WHERE user_id = %s AND project_id = %s ORDER BY created_at DESC;"
        with get_conn() as conn:
            return conn.execute(sql, (user_id, project_id)).fetchall()
    else:
        sql = "SELECT id, query_text, municipality, top_k, answer_text, citations, model, latency_ms, created_at, project_id, session_id FROM query_log WHERE user_id = %s ORDER BY created_at DESC;"
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

    Row ids come from the client, so the ON CONFLICT branch is scoped to this
    project -- an editor on one project cannot overwrite another project's row.

    Raises:
        PermissionError: When any id already belongs to a different project.
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
        WHERE project_room_scans.project_id = %(project_id)s
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
            updated = conn.execute(
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
            ).fetchone()
            # An ON CONFLICT whose ownership predicate fails updates nothing and
            # returns nothing — that is the only way to get no row back here.
            if updated is None:
                raise PermissionError(
                    f"Scan id belongs to another project: {scan['id']}"
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
    """
    Upsert derived summaries into the user's scan library.

    Row ids come from the client, so every write is scoped to the caller: the
    ON CONFLICT branch only touches rows this user already owns.

    Raises:
        PermissionError: When any id belongs to a different user's library.
    """
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
        WHERE user_room_scans.user_id = %(user_id)s
        RETURNING *;
    """
    with get_conn() as conn:
        for scan in scans:
            updated = conn.execute(
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
            ).fetchone()
            # An ON CONFLICT whose ownership predicate fails updates nothing and
            # returns nothing — that is the only way to get no row back here.
            if updated is None:
                raise PermissionError(
                    f"Scan id belongs to another user's library: {scan['id']}"
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
    room_scan_id: UUID | None,
    input_tokens: int,
    output_tokens: int,
    model: str,
    kind: str = "design_intent",
) -> dict[str, Any]:
    """
    Log one metered call for accounting.

    Args:
        kind: design_intent for LLM overlay parses, room_image for generative
            preview images (migration 036). room_scan_id is None for the latter.
    """
    sql = """
        INSERT INTO design_intent_usage (
            user_id, project_id, room_scan_id,
            input_tokens, output_tokens, model, kind
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (user_id, project_id, room_scan_id, input_tokens, output_tokens, model, kind),
        ).fetchone()
        conn.commit()
    return row


def sum_design_intent_tokens(user_id: UUID, *, since: datetime) -> int:
    """Sum input + output tokens for a user's design-intent calls since a timestamp."""
    sql = """
        SELECT COALESCE(SUM(input_tokens + output_tokens), 0) AS total
        FROM design_intent_usage
        WHERE user_id = %s AND created_at >= %s AND kind = 'design_intent';
    """
    with get_conn() as conn:
        row = conn.execute(sql, (user_id, since)).fetchone()
    return int(row["total"]) if row else 0


def count_design_intent_usage(user_id: UUID, *, since: datetime, kind: str) -> int:
    """Count a user's metered calls of one kind since a timestamp."""
    sql = """
        SELECT COUNT(*) AS total
        FROM design_intent_usage
        WHERE user_id = %s AND created_at >= %s AND kind = %s;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (user_id, since, kind)).fetchone()
    return int(row["total"]) if row else 0


# ════════════════════════════════════════════════
#  AGENT TRACES  (migration 026)
# ════════════════════════════════════════════════
# Backing store for audit/logger.py. Callers go through that module rather
# than these helpers directly -- it owns cost math and the @traced decorator.


def insert_agent_run(
    *,
    entrypoint: str,
    user_id: UUID | None = None,
    project_id: UUID | None = None,
    intent: str | None = None,
    persona: str | None = None,
    request_id: str | None = None,
    session_id: str | None = None,
    model_default: str | None = None,
) -> dict[str, Any]:
    """Open a run row and return it (tokens/cost are filled in on finish)."""
    sql = """
        INSERT INTO agent_runs (
            entrypoint, user_id, project_id, intent,
            persona, request_id, session_id, model_default
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (
                entrypoint,
                user_id,
                project_id,
                intent,
                persona,
                request_id,
                session_id,
                model_default,
            ),
        ).fetchone()
        conn.commit()
    return row


def finish_agent_run(
    run_id: UUID,
    *,
    outcome: str,
    latency_ms: int | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    """
    Close a run, rolling token and cost totals up from its steps.

    Aggregating in SQL rather than in Python keeps the totals correct even
    when a step is written by a different process or a retry.
    """
    sql = """
        UPDATE agent_runs AS r
        SET outcome            = %s,
            latency_ms         = %s,
            error              = %s,
            finished_at        = now(),
            tokens_in          = COALESCE(s.tokens_in, 0),
            tokens_out         = COALESCE(s.tokens_out, 0),
            tokens_cache_read  = COALESCE(s.tokens_cache_read, 0),
            tokens_cache_write = COALESCE(s.tokens_cache_write, 0),
            cost_usd           = COALESCE(s.cost_usd, 0)
        FROM (
            SELECT SUM(tokens_in)          AS tokens_in,
                   SUM(tokens_out)         AS tokens_out,
                   SUM(tokens_cache_read)  AS tokens_cache_read,
                   SUM(tokens_cache_write) AS tokens_cache_write,
                   SUM(cost_usd)           AS cost_usd
            FROM agent_steps
            WHERE run_id = %s
        ) AS s
        WHERE r.id = %s
        RETURNING r.*;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql, (outcome, latency_ms, error, run_id, run_id)
        ).fetchone()
        conn.commit()
    return row


def insert_agent_step(
    *,
    run_id: UUID,
    agent_name: str,
    step_index: int = 0,
    parent_step_id: UUID | None = None,
    model: str | None = None,
    deterministic: bool = False,
    react_iterations: int = 0,
    autonomy_level: str | None = None,
    prompt_version: str | None = None,
    prompt_fragment_ids: list[str] | None = None,
    input_hash: str | None = None,
    artifact_refs: list[str] | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    tokens_cache_read: int = 0,
    tokens_cache_write: int = 0,
    cost_usd: float = 0.0,
    latency_ms: int | None = None,
    status: str = "ok",
    error: str | None = None,
) -> dict[str, Any]:
    """Record one agent invocation within a run."""
    sql = """
        INSERT INTO agent_steps (
            run_id, agent_name, step_index, parent_step_id, model,
            deterministic, react_iterations, autonomy_level, prompt_version,
            prompt_fragment_ids, input_hash, artifact_refs,
            tokens_in, tokens_out, tokens_cache_read, tokens_cache_write,
            cost_usd, latency_ms, status, error
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s
        )
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (
                run_id,
                agent_name,
                step_index,
                parent_step_id,
                model,
                deterministic,
                react_iterations,
                autonomy_level,
                prompt_version,
                prompt_fragment_ids or [],
                input_hash,
                artifact_refs or [],
                tokens_in,
                tokens_out,
                tokens_cache_read,
                tokens_cache_write,
                cost_usd,
                latency_ms,
                status,
                error,
            ),
        ).fetchone()
        conn.commit()
    return row


_RUN_ANNOTATABLE = frozenset(
    {"user_id", "project_id", "intent", "persona", "model_default", "session_id"}
)


def annotate_agent_run(run_id: UUID, **fields: Any) -> dict[str, Any] | None:
    """
    Fill in run metadata that is only known partway through a request.

    Column names are whitelisted rather than interpolated freely -- these are
    the only fields a caller may set after the run opens.
    """
    updates = {k: v for k, v in fields.items() if k in _RUN_ANNOTATABLE}
    if not updates:
        return None
    assignments = ", ".join(f"{col} = %({col})s" for col in updates)
    params: dict[str, Any] = {**updates, "run_id": run_id}
    sql = f"UPDATE agent_runs SET {assignments} WHERE id = %(run_id)s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


def get_agent_run(run_id: UUID) -> dict[str, Any] | None:
    """Fetch a single run row."""
    sql = "SELECT * FROM agent_runs WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (run_id,)).fetchone()


def list_agent_steps(run_id: UUID) -> list[dict[str, Any]]:
    """Fetch every step in a run, in execution order."""
    sql = """
        SELECT * FROM agent_steps
        WHERE run_id = %s
        ORDER BY step_index, created_at;
    """
    with get_conn() as conn:
        return conn.execute(sql, (run_id,)).fetchall()


def agent_scorecard(*, since: datetime) -> list[dict[str, Any]]:
    """
    Per-agent rollup for the superadmin dashboard.

    deterministic_rate is the Crystallizer KPI -- the share of calls served
    without a model.
    """
    sql = """
        SELECT agent_name,
               COUNT(*)                                        AS calls,
               SUM(cost_usd)                                   AS cost_usd,
               SUM(tokens_in + tokens_out)                     AS tokens,
               SUM(tokens_cache_read)                          AS tokens_cache_read,
               AVG(react_iterations)                           AS avg_react_iterations,
               AVG(deterministic::int)                         AS deterministic_rate,
               AVG(latency_ms)                                 AS avg_latency_ms,
               PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY latency_ms)  AS p50_latency_ms,
               PERCENTILE_DISC(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
               AVG((status <> 'ok')::int)                       AS error_rate
        FROM agent_steps
        WHERE created_at >= %s
        GROUP BY agent_name
        ORDER BY cost_usd DESC NULLS LAST;
    """
    with get_conn() as conn:
        return conn.execute(sql, (since,)).fetchall()


# ── Corrections ──────────────────────────────────────────────


def insert_agent_correction(
    *,
    source: str,
    run_id: UUID | None = None,
    step_id: UUID | None = None,
    attributed_agent: str | None = None,
    attribution_confidence: float | None = None,
    severity: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    expected: str | None = None,
    actual: str | None = None,
    notes: str | None = None,
    confirmed: bool = False,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    """Record a human correction. Training data for the Optimizer."""
    sql = """
        INSERT INTO agent_corrections (
            source, run_id, step_id, attributed_agent, attribution_confidence,
            severity, entity_type, entity_id, expected, actual, notes,
            confirmed, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (
                source,
                run_id,
                step_id,
                attributed_agent,
                attribution_confidence,
                severity,
                entity_type,
                entity_id,
                expected,
                actual,
                notes,
                confirmed,
                created_by,
            ),
        ).fetchone()
        conn.commit()
    return row


def correction_rate_by_agent(*, since: datetime) -> list[dict[str, Any]]:
    """Confirmed corrections per agent since a timestamp."""
    sql = """
        SELECT attributed_agent AS agent_name,
               COUNT(*) FILTER (WHERE confirmed) AS confirmed_corrections,
               COUNT(*)                          AS total_corrections
        FROM agent_corrections
        WHERE created_at >= %s AND attributed_agent IS NOT NULL
        GROUP BY attributed_agent
        ORDER BY confirmed_corrections DESC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (since,)).fetchall()


def list_agent_corrections(
    *, confirmed: bool | None = None, source: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """Corrections for the dashboard confirm-queue, newest first.

    ``confirmed=False`` is the Performance Review triage queue — attributions a
    human has not yet confirmed. ``None`` returns both.
    """
    clauses, params = [], []
    if confirmed is not None:
        clauses.append("confirmed = %s")
        params.append(confirmed)
    if source is not None:
        clauses.append("source = %s")
        params.append(source)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT * FROM agent_corrections
        {where}
        ORDER BY created_at DESC
        LIMIT %s;
    """
    params.append(limit)
    with get_conn() as conn:
        return conn.execute(sql, tuple(params)).fetchall()


def confirm_agent_correction(
    correction_id: UUID,
    *,
    attributed_agent: str | None = None,
    confirmed_by: UUID | None = None,
) -> dict[str, Any] | None:
    """Confirm a correction (the human sign-off), optionally re-attributing it.

    This is what turns a Performance Review proposal into training data. When
    ``attributed_agent`` is given it overwrites the model's guess (the human
    assigns blame on a low-confidence row); otherwise the existing value stands.
    """
    sql = """
        UPDATE agent_corrections
        SET confirmed        = true,
            attributed_agent = COALESCE(%s, attributed_agent),
            created_by       = COALESCE(%s, created_by)
        WHERE id = %s
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (attributed_agent, confirmed_by, correction_id)).fetchone()
        conn.commit()
    return row


# ── Answer feedback ──────────────────────────────────────────


def upsert_answer_feedback(
    *,
    run_id: UUID,
    rating: str,
    user_id: UUID | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """Record (or update) a user's thumbs up/down on an answer's run.

    One vote per (run_id, user_id): re-voting flips the rating or edits the
    comment in place rather than stacking rows. Raises on a foreign-key
    violation when ``run_id`` has no matching agent_runs row — the caller
    validates the run exists first.
    """
    sql = """
        INSERT INTO answer_feedback (run_id, user_id, rating, comment)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (run_id, user_id)
        DO UPDATE SET rating     = EXCLUDED.rating,
                      comment    = EXCLUDED.comment,
                      updated_at = now()
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (run_id, user_id, rating, comment)).fetchone()
        conn.commit()
    return row


def answer_feedback_counts(*, since: datetime) -> dict[str, int]:
    """Return {'up': n, 'down': m} answer-feedback totals since a timestamp."""
    sql = """
        SELECT rating, COUNT(*) AS n
        FROM answer_feedback
        WHERE created_at >= %s
        GROUP BY rating;
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (since,)).fetchall()
    counts = {"up": 0, "down": 0}
    for row in rows:
        counts[row["rating"]] = int(row["n"])
    return counts


def list_downvotes_without_review(
    *, since: datetime, limit: int = 100
) -> list[dict[str, Any]]:
    """Down-votes whose run has no answer-level correction yet.

    The work queue for the Performance Review batch driver: a down-vote is
    'reviewed' once an ``agent_corrections`` row with ``source='answer'`` exists
    for its run. Newest first.
    """
    sql = """
        SELECT af.*
        FROM answer_feedback af
        WHERE af.rating = 'down'
          AND af.created_at >= %s
          AND NOT EXISTS (
              SELECT 1 FROM agent_corrections ac
              WHERE ac.run_id = af.run_id AND ac.source = 'answer'
          )
        ORDER BY af.created_at DESC
        LIMIT %s;
    """
    with get_conn() as conn:
        return conn.execute(sql, (since, limit)).fetchall()


# ── Action items ─────────────────────────────────────────────


def upsert_action_item(
    *,
    source_agent: str,
    kind: str,
    title: str,
    severity: str = "medium",
    blocking: bool = False,
    run_id: UUID | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    evidence: dict[str, Any] | None = None,
    proposed_action: str | None = None,
) -> dict[str, Any] | None:
    """
    File an item needing human action, deduped on the open-item unique index.

    Re-filing an item that is already open or acknowledged refreshes its
    evidence instead of creating a duplicate -- a nightly anomaly sweep
    would otherwise pile up one row per run.
    """
    import json as _json

    sql = """
        INSERT INTO agent_action_items (
            source_agent, kind, severity, blocking, run_id,
            entity_type, entity_id, title, evidence, proposed_action
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        -- Must match uq_agent_action_items_open_entity for Postgres to infer
        -- the partial index (migration 026).
        ON CONFLICT (source_agent, kind, entity_type, entity_id)
            WHERE status IN ('open', 'acknowledged')
        DO UPDATE SET evidence   = EXCLUDED.evidence,
                      severity   = EXCLUDED.severity,
                      title      = EXCLUDED.title,
                      created_at = now()
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql,
            (
                source_agent,
                kind,
                severity,
                blocking,
                run_id,
                # '' rather than NULL so the dedupe index applies to
                # entity-less items too -- see migration 026.
                entity_type or "",
                entity_id or "",
                title,
                _json.dumps(evidence or {}),
                proposed_action,
            ),
        ).fetchone()
        conn.commit()
    return row


def list_action_items(
    *,
    status: str = "open",
    source_agent: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List action items for the dashboard queue, most severe first."""
    sql = """
        SELECT * FROM agent_action_items
        WHERE status = %s
          AND (%s::text IS NULL OR source_agent = %s)
        ORDER BY CASE severity
                     WHEN 'critical' THEN 0
                     WHEN 'high'     THEN 1
                     WHEN 'medium'   THEN 2
                     ELSE 3
                 END,
                 created_at DESC
        LIMIT %s;
    """
    with get_conn() as conn:
        return conn.execute(
            sql, (status, source_agent, source_agent, limit)
        ).fetchall()


def resolve_action_item(
    item_id: UUID,
    *,
    status: str,
    resolved_by: UUID,
    resolution_note: str | None = None,
) -> dict[str, Any] | None:
    """Resolve or dismiss an action item."""
    sql = """
        UPDATE agent_action_items
        SET status          = %s,
            resolved_by     = %s,
            resolved_at     = now(),
            resolution_note = %s
        WHERE id = %s
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql, (status, resolved_by, resolution_note, item_id)
        ).fetchone()
        conn.commit()
    return row


# ── Autonomy ─────────────────────────────────────────────────


def get_agent_autonomy(agent_name: str, scope: str = "default") -> dict[str, Any] | None:
    """Fetch the autonomy row for an agent + scope. None means unregistered."""
    sql = """
        SELECT * FROM agent_autonomy
        WHERE agent_name = %s AND scope = %s;
    """
    with get_conn() as conn:
        return conn.execute(sql, (agent_name, scope)).fetchone()


def list_agent_autonomy() -> list[dict[str, Any]]:
    """Every autonomy row, for the dashboard control panel."""
    sql = "SELECT * FROM agent_autonomy ORDER BY agent_name, scope;"
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def set_agent_autonomy(
    agent_name: str,
    scope: str,
    *,
    current_level: str,
    updated_by: UUID | None = None,
) -> dict[str, Any] | None:
    """
    Set an agent's autonomy level, clamped to its ceiling in SQL.

    The clamp lives here as well as in the runtime so that a direct API call
    cannot exceed a ceiling the dashboard merely hides. Returns None when the
    requested level is above max_level.
    """
    sql = """
        UPDATE agent_autonomy
        SET current_level = %s,
            updated_by    = %s,
            updated_at    = now()
        WHERE agent_name = %s
          AND scope = %s
          AND CASE %s WHEN 'L0' THEN 0 WHEN 'L1' THEN 1
                      WHEN 'L2' THEN 2 ELSE 3 END
            <= CASE max_level WHEN 'L0' THEN 0 WHEN 'L1' THEN 1
                              WHEN 'L2' THEN 2 ELSE 3 END
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql, (current_level, updated_by, agent_name, scope, current_level)
        ).fetchone()
        conn.commit()
    return row


# ════════════════════════════════════════════════
#  MEDIA REFS  (Media Curator, agent #17)
# ════════════════════════════════════════════════

def fetch_media_refs(
    task_key: str,
    *,
    jurisdiction: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """
    Fetch active, vetted video links for a task, jurisdiction-aware.

    The deterministic sourced path for the Media Curator: every row returned is a
    hand-verified link, so the "zero unsourced URLs" gate holds by construction.
    Jurisdiction-specific rows sort ahead of national ones (NULL jurisdiction),
    then most-recently-verified first. Returns at most ``limit`` rows.

    Args:
        task_key: Normalized task, e.g. ``install_gfci_outlet``.
        jurisdiction: Municipality to prefer (matches ``documents.municipality``),
            or None to take national how-tos only.
        limit: Max rows to return.

    Returns:
        Row dicts (id, task_key, title, url, provider, jurisdiction,
        relevance_note, last_verified_at, active, created_at), best match first.
    """
    sql = """
        SELECT *
        FROM media_refs
        WHERE active
          AND task_key = %s
          AND (jurisdiction IS NULL OR jurisdiction = %s)
        ORDER BY
            (jurisdiction IS NOT NULL) DESC,       -- jurisdiction match before national
            last_verified_at DESC NULLS LAST,
            created_at DESC
        LIMIT %s;
    """
    with get_conn() as conn:
        return conn.execute(sql, (task_key, jurisdiction, limit)).fetchall()


def list_media_refs(*, active_only: bool = True) -> list[dict[str, Any]]:
    """List curated media_refs rows (all of them), newest first.

    Used by the transcript-ingest driver to walk every vetted video. Unlike
    ``fetch_media_refs`` (task-scoped, jurisdiction-aware, capped), this returns
    the whole table.
    """
    where = "WHERE active" if active_only else ""
    sql = f"SELECT * FROM media_refs {where} ORDER BY created_at DESC;"
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def fetch_media_refs_for_how_to_docs(doc_ids: list[str]) -> list[dict[str, Any]]:
    """Map how-to transcript doc_ids back to their media_refs display rows.

    A transcript document's ``source_url`` equals its ``media_refs.url`` (the
    ingest uses the same URL), so this joins retrieved how-to chunks
    (``content_class='how_to'``) to the curated link metadata (title, relevance
    note). Powers *semantic* links: any ingested video surfaces as a link from a
    semantic transcript hit, with **no hand-assigned task_key** — the scaling
    unlock for channel ingest. Each row carries its ``doc_id`` so the caller can
    preserve retrieval (similarity) order.
    """
    if not doc_ids:
        return []
    sql = """
        SELECT d.doc_id AS doc_id, m.*
        FROM media_refs m
        JOIN documents d ON d.source_url = m.url
        WHERE d.doc_id = ANY(%s) AND m.active;
    """
    with get_conn() as conn:
        return conn.execute(sql, (doc_ids,)).fetchall()


def insert_media_ref(
    *,
    task_key: str,
    title: str,
    url: str,
    provider: str = "youtube",
    jurisdiction: str | None = None,
    relevance_note: str | None = None,
    last_verified_at: datetime | None = None,
    active: bool = True,
    channel_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Insert one curated video link (seed script + channel crawler).

    Deduped on (task_key, url): re-inserting the same link is a no-op that returns
    None (the row already exists). ``channel_id`` marks a crawled row's source
    channel (NULL = hand-added). All curated links enter the corpus here; the
    Media Curator never writes.
    """
    sql = """
        INSERT INTO media_refs
            (task_key, title, url, provider, jurisdiction, relevance_note,
             last_verified_at, active, channel_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING *;
    """
    params = (
        task_key, title, url, provider, jurisdiction, relevance_note,
        last_verified_at, active, channel_id,
    )
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


# ════════════════════════════════════════════════
#  MEDIA CHANNELS  (H2-6 channel crawl)
# ════════════════════════════════════════════════

def insert_media_channel(
    *,
    channel_id: str,
    name: str,
    jurisdiction: str | None = None,
    vetted_by: str | None = None,
    active: bool = True,
) -> dict[str, Any] | None:
    """Add (or update) a vetted YouTube channel. Deduped on channel_id."""
    sql = """
        INSERT INTO media_channels (channel_id, name, jurisdiction, vetted_by, active)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (channel_id) DO UPDATE SET
            name = EXCLUDED.name,
            jurisdiction = EXCLUDED.jurisdiction,
            vetted_by = EXCLUDED.vetted_by,
            active = EXCLUDED.active
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(
            sql, (channel_id, name, jurisdiction, vetted_by, active)
        ).fetchone()
        conn.commit()
    return row


def list_media_channels(*, active_only: bool = True) -> list[dict[str, Any]]:
    """List vetted channels, newest first."""
    where = "WHERE active" if active_only else ""
    sql = f"SELECT * FROM media_channels {where} ORDER BY created_at DESC;"
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def touch_media_channel_crawled(channel_id: str) -> None:
    """Stamp ``last_crawled_at = now()`` for a channel after a successful crawl."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE media_channels SET last_crawled_at = now() WHERE channel_id = %s;",
            (channel_id,),
        )
        conn.commit()


def delete_placeholder_media_refs() -> int:
    """Delete un-vetted placeholder seed rows (URL still carries the sentinel).

    A cleanup for rows seeded before their placeholder links were replaced with
    verified ones. Keys on the ``REPLACE_WITH_VERIFIED_ID`` URL sentinel only — not
    the word "replace", which is legitimate in a title like "How to replace a
    faucet". media_refs is a curated helper table, not the governed document
    corpus, so a hard delete is appropriate here (the "never delete a document"
    rule is about ``documents``/``registry.json``, not this table). Returns the
    number of rows removed.
    """
    sql = "DELETE FROM media_refs WHERE url ILIKE %s;"
    with get_conn() as conn:
        cur = conn.execute(sql, ("%REPLACE_WITH_VERIFIED_ID%",))
        removed = cur.rowcount
        conn.commit()
    return removed


# ════════════════════════════════════════════════
#  CONTRACTOR PROFILES + LICENSES  (migration 044)
# ════════════════════════════════════════════════

def create_contractor_profile(
    *,
    user_id: UUID,
    business_name: str,
    contact_name: str | None = None,
    phone: str | None = None,
    trades: list[str] | None = None,
    service_municipalities: list[str] | None = None,
    bio: str | None = None,
    years_in_business: int | None = None,
) -> dict[str, Any]:
    """Create a contractor profile for an existing user (one per user)."""
    sql = """
        INSERT INTO contractor_profiles (
            user_id, business_name, contact_name, phone,
            trades, service_municipalities, bio, years_in_business
        )
        VALUES (
            %(user_id)s, %(business_name)s, %(contact_name)s, %(phone)s,
            %(trades)s, %(service_municipalities)s, %(bio)s, %(years_in_business)s
        )
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {
            "user_id": user_id,
            "business_name": business_name,
            "contact_name": contact_name,
            "phone": phone,
            "trades": trades or [],
            "service_municipalities": service_municipalities or [],
            "bio": bio,
            "years_in_business": years_in_business,
        }).fetchone()
        conn.commit()
    log.info("Created contractor profile for user_id=%s", user_id)
    return row


def get_contractor_profile_by_user(user_id: UUID) -> dict[str, Any] | None:
    """Fetch the caller's own contractor profile, if any."""
    sql = "SELECT * FROM contractor_profiles WHERE user_id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (user_id,)).fetchone()


def get_contractor_profile(contractor_profile_id: UUID) -> dict[str, Any] | None:
    """Fetch a contractor profile by its own id."""
    sql = "SELECT * FROM contractor_profiles WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (contractor_profile_id,)).fetchone()


def contractor_profile_exists(user_id: UUID) -> bool:
    """True if the user has already created a contractor profile."""
    sql = "SELECT 1 FROM contractor_profiles WHERE user_id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (user_id,)).fetchone() is not None


def update_contractor_profile(
    user_id: UUID,
    *,
    business_name: str | None = None,
    contact_name: str | None = None,
    phone: str | None = None,
    trades: list[str] | None = None,
    service_municipalities: list[str] | None = None,
    bio: str | None = None,
    years_in_business: int | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    """Update mutable contractor-profile fields, keyed by user_id (1:1)."""
    assignments: list[str] = []
    params: dict[str, Any] = {"user_id": user_id}
    if business_name is not None:
        assignments.append("business_name = %(business_name)s")
        params["business_name"] = business_name
    if contact_name is not None:
        assignments.append("contact_name = %(contact_name)s")
        params["contact_name"] = contact_name
    if phone is not None:
        assignments.append("phone = %(phone)s")
        params["phone"] = phone
    if trades is not None:
        assignments.append("trades = %(trades)s")
        params["trades"] = trades
    if service_municipalities is not None:
        assignments.append("service_municipalities = %(service_municipalities)s")
        params["service_municipalities"] = service_municipalities
    if bio is not None:
        assignments.append("bio = %(bio)s")
        params["bio"] = bio
    if years_in_business is not None:
        assignments.append("years_in_business = %(years_in_business)s")
        params["years_in_business"] = years_in_business
    if is_active is not None:
        assignments.append("is_active = %(is_active)s")
        params["is_active"] = is_active
    if not assignments:
        return get_contractor_profile_by_user(user_id)
    sql = f"UPDATE contractor_profiles SET {', '.join(assignments)} WHERE user_id = %(user_id)s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


def create_contractor_license(
    *,
    contractor_profile_id: UUID,
    trade: str,
    license_number: str,
    expiration_date: date,
    issuing_authority: str | None = None,
    insurance_provider: str | None = None,
    insurance_policy_number: str | None = None,
    insurance_coverage_amount: float | None = None,
    insurance_expiration_date: date | None = None,
) -> dict[str, Any]:
    """Add a license/insurance record to a contractor profile."""
    sql = """
        INSERT INTO contractor_licenses (
            contractor_profile_id, trade, license_number, expiration_date,
            issuing_authority, insurance_provider, insurance_policy_number,
            insurance_coverage_amount, insurance_expiration_date
        )
        VALUES (
            %(contractor_profile_id)s, %(trade)s, %(license_number)s, %(expiration_date)s,
            %(issuing_authority)s, %(insurance_provider)s, %(insurance_policy_number)s,
            %(insurance_coverage_amount)s, %(insurance_expiration_date)s
        )
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {
            "contractor_profile_id": contractor_profile_id,
            "trade": trade,
            "license_number": license_number,
            "expiration_date": expiration_date,
            "issuing_authority": issuing_authority,
            "insurance_provider": insurance_provider,
            "insurance_policy_number": insurance_policy_number,
            "insurance_coverage_amount": insurance_coverage_amount,
            "insurance_expiration_date": insurance_expiration_date,
        }).fetchone()
        conn.commit()
    return row


def list_contractor_licenses(contractor_profile_id: UUID) -> list[dict[str, Any]]:
    """All license records for a contractor profile, most-recently-added first."""
    sql = """
        SELECT * FROM contractor_licenses
        WHERE contractor_profile_id = %s
        ORDER BY created_at DESC;
    """
    with get_conn() as conn:
        return conn.execute(sql, (contractor_profile_id,)).fetchall()


def get_contractor_license(license_id: UUID) -> dict[str, Any] | None:
    """Fetch a single license record by id."""
    sql = "SELECT * FROM contractor_licenses WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (license_id,)).fetchone()


def update_contractor_license(
    license_id: UUID,
    *,
    trade: str | None = None,
    license_number: str | None = None,
    expiration_date: date | None = None,
    issuing_authority: str | None = None,
    insurance_provider: str | None = None,
    insurance_policy_number: str | None = None,
    insurance_coverage_amount: float | None = None,
    insurance_expiration_date: date | None = None,
) -> dict[str, Any] | None:
    """Update mutable fields on a license record."""
    assignments: list[str] = []
    params: dict[str, Any] = {"id": license_id}
    for field, value in (
        ("trade", trade),
        ("license_number", license_number),
        ("expiration_date", expiration_date),
        ("issuing_authority", issuing_authority),
        ("insurance_provider", insurance_provider),
        ("insurance_policy_number", insurance_policy_number),
        ("insurance_coverage_amount", insurance_coverage_amount),
        ("insurance_expiration_date", insurance_expiration_date),
    ):
        if value is not None:
            assignments.append(f"{field} = %({field})s")
            params[field] = value
    if not assignments:
        return get_contractor_license(license_id)
    sql = f"UPDATE contractor_licenses SET {', '.join(assignments)} WHERE id = %(id)s RETURNING *;"
    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
        conn.commit()
    return row


def delete_contractor_license(license_id: UUID) -> bool:
    """Remove a license record."""
    sql = "DELETE FROM contractor_licenses WHERE id = %s;"
    with get_conn() as conn:
        cur = conn.execute(sql, (license_id,))
        conn.commit()
    return cur.rowcount > 0


def has_valid_license(contractor_profile_id: UUID) -> bool:
    """True if the contractor has at least one non-expired license on file."""
    sql = """
        SELECT 1 FROM contractor_licenses
        WHERE contractor_profile_id = %s AND expiration_date >= CURRENT_DATE
        LIMIT 1;
    """
    with get_conn() as conn:
        return conn.execute(sql, (contractor_profile_id,)).fetchone() is not None


# ════════════════════════════════════════════════
#  LABOR RATE BENCHMARKS  (migration 038)
# ════════════════════════════════════════════════

def list_labor_rate_benchmarks(trade: str | None = None) -> list[dict[str, Any]]:
    """Seeded hourly-rate ranges, optionally filtered to one trade."""
    if trade:
        sql = "SELECT * FROM labor_rate_benchmarks WHERE trade = %s ORDER BY trade;"
        with get_conn() as conn:
            return conn.execute(sql, (trade,)).fetchall()
    sql = "SELECT * FROM labor_rate_benchmarks ORDER BY trade;"
    with get_conn() as conn:
        return conn.execute(sql).fetchall()


def get_labor_rate_benchmark(trade: str, region: str = "DFW") -> dict[str, Any] | None:
    """A single trade/region benchmark row, or None if unseeded."""
    sql = "SELECT * FROM labor_rate_benchmarks WHERE trade = %s AND region = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (trade, region)).fetchone()


def insert_labor_rate_benchmark(
    *,
    trade: str,
    region: str = "DFW",
    low_hourly_rate: float,
    high_hourly_rate: float,
    source: str,
    effective_date: date | None = None,
) -> dict[str, Any] | None:
    """Insert one benchmark row (seed script). Deduped on (trade, region)."""
    sql = """
        INSERT INTO labor_rate_benchmarks
            (trade, region, low_hourly_rate, high_hourly_rate, source, effective_date)
        VALUES
            (%(trade)s, %(region)s, %(low_hourly_rate)s, %(high_hourly_rate)s, %(source)s, %(effective_date)s)
        ON CONFLICT (trade, region) DO NOTHING
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, {
            "trade": trade,
            "region": region,
            "low_hourly_rate": low_hourly_rate,
            "high_hourly_rate": high_hourly_rate,
            "source": source,
            "effective_date": effective_date,
        }).fetchone()
        conn.commit()
    return row


# ════════════════════════════════════════════════
#  BIDS  (migration 038)
# ════════════════════════════════════════════════

def create_bid(
    *,
    project_id: UUID,
    contractor_profile_id: UUID,
    license_id: UUID,
    total_price: float,
    line_items: list[dict[str, Any]],
    labor_total: float | None = None,
    material_total: float | None = None,
    allowances: list[dict[str, Any]] | None = None,
    exclusions: list[dict[str, Any]] | None = None,
    payment_schedule: list[dict[str, Any]] | None = None,
    permit_responsibility: str | None = None,
    timeline_start: date | None = None,
    timeline_end: date | None = None,
    timeline_notes: str | None = None,
    warranty_text: str | None = None,
    warranty_years: float | None = None,
    change_order_terms: str | None = None,
    lien_waiver_included: bool = False,
    materials_source: str = "unspecified",
    materials_source_connector: str | None = None,
    materials_source_notes: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a bid header + its line items in one transaction.

    total_price/labor_total/material_total are trusted from the caller (the
    service layer computes them from line_items — see bids/service.py), not
    recomputed here; this function is pure persistence.
    """
    import json as _json

    sql_bid = """
        INSERT INTO bids (
            project_id, contractor_profile_id, license_id, total_price,
            labor_total, material_total, allowances, exclusions, payment_schedule,
            permit_responsibility, timeline_start, timeline_end, timeline_notes,
            warranty_text, warranty_years, change_order_terms, lien_waiver_included,
            materials_source, materials_source_connector, materials_source_notes,
            notes, submitted_at
        )
        VALUES (
            %(project_id)s, %(contractor_profile_id)s, %(license_id)s, %(total_price)s,
            %(labor_total)s, %(material_total)s, %(allowances)s::jsonb, %(exclusions)s::jsonb, %(payment_schedule)s::jsonb,
            %(permit_responsibility)s, %(timeline_start)s, %(timeline_end)s, %(timeline_notes)s,
            %(warranty_text)s, %(warranty_years)s, %(change_order_terms)s, %(lien_waiver_included)s,
            %(materials_source)s, %(materials_source_connector)s, %(materials_source_notes)s,
            %(notes)s, now()
        )
        RETURNING *;
    """
    sql_line = """
        INSERT INTO bid_line_items (
            bid_id, line_index, description, quantity, unit, unit_price,
            labor_amount, material_amount, labor_hours, canonical_work_item
        )
        VALUES (
            %(bid_id)s, %(line_index)s, %(description)s, %(quantity)s, %(unit)s, %(unit_price)s,
            %(labor_amount)s, %(material_amount)s, %(labor_hours)s, %(canonical_work_item)s
        );
    """
    with get_conn() as conn:
        bid = conn.execute(sql_bid, {
            "project_id": project_id,
            "contractor_profile_id": contractor_profile_id,
            "license_id": license_id,
            "total_price": total_price,
            "labor_total": labor_total,
            "material_total": material_total,
            "allowances": _json.dumps(allowances or []),
            "exclusions": _json.dumps(exclusions or []),
            "payment_schedule": _json.dumps(payment_schedule or []),
            "permit_responsibility": permit_responsibility,
            "timeline_start": timeline_start,
            "timeline_end": timeline_end,
            "timeline_notes": timeline_notes,
            "warranty_text": warranty_text,
            "warranty_years": warranty_years,
            "change_order_terms": change_order_terms,
            "lien_waiver_included": lien_waiver_included,
            "materials_source": materials_source,
            "materials_source_connector": materials_source_connector,
            "materials_source_notes": materials_source_notes,
            "notes": notes,
        }).fetchone()
        for idx, item in enumerate(line_items):
            conn.execute(sql_line, {
                "bid_id": bid["id"],
                "line_index": idx,
                "description": item["description"],
                "quantity": item["quantity"],
                "unit": item["unit"],
                "unit_price": item["unit_price"],
                "labor_amount": item.get("labor_amount", 0),
                "material_amount": item.get("material_amount", 0),
                "labor_hours": item.get("labor_hours"),
                "canonical_work_item": item.get("canonical_work_item"),
            })
        conn.commit()
    log.info("Created bid %s on project=%s contractor=%s", bid["id"], project_id, contractor_profile_id)
    return bid


def list_bids_for_project(project_id: UUID) -> list[dict[str, Any]]:
    """All bids on a project, newest first — homeowner/staff view."""
    sql = "SELECT * FROM bids WHERE project_id = %s ORDER BY created_at DESC;"
    with get_conn() as conn:
        return conn.execute(sql, (project_id,)).fetchall()


def list_bids_for_contractor(contractor_profile_id: UUID) -> list[dict[str, Any]]:
    """A contractor's own bid history, newest first."""
    sql = "SELECT * FROM bids WHERE contractor_profile_id = %s ORDER BY created_at DESC;"
    with get_conn() as conn:
        return conn.execute(sql, (contractor_profile_id,)).fetchall()


def get_bid(bid_id: UUID) -> dict[str, Any] | None:
    """Fetch a bid header by id."""
    sql = "SELECT * FROM bids WHERE id = %s;"
    with get_conn() as conn:
        return conn.execute(sql, (bid_id,)).fetchone()


def list_bid_line_items(bid_id: UUID) -> list[dict[str, Any]]:
    """A bid's line items in submission order."""
    sql = "SELECT * FROM bid_line_items WHERE bid_id = %s ORDER BY line_index;"
    with get_conn() as conn:
        return conn.execute(sql, (bid_id,)).fetchall()


def withdraw_bid(bid_id: UUID) -> dict[str, Any] | None:
    """Contractor withdraws their own submitted bid. No-op (returns None) if
    the bid isn't currently 'submitted' (already withdrawn/declined/awarded)."""
    sql = """
        UPDATE bids SET status = 'withdrawn', decided_at = now()
        WHERE id = %s AND status = 'submitted'
        RETURNING *;
    """
    with get_conn() as conn:
        row = conn.execute(sql, (bid_id,)).fetchone()
        conn.commit()
    return row


def award_bid(project_id: UUID, bid_id: UUID) -> dict[str, Any] | None:
    """Award one bid: it -> awarded, every other submitted bid on the project
    -> declined, project marketplace_status -> awarded. One transaction,
    modeled on transfer_project_ownership's "multiple statements, one commit"."""
    with get_conn() as conn:
        bid = conn.execute(
            "UPDATE bids SET status = 'awarded', decided_at = now() WHERE id = %s AND project_id = %s RETURNING *;",
            (bid_id, project_id),
        ).fetchone()
        if not bid:
            return None
        conn.execute(
            """
            UPDATE bids SET status = 'declined', decided_at = now()
            WHERE project_id = %s AND id != %s AND status = 'submitted';
            """,
            (project_id, bid_id),
        )
        conn.execute(
            "UPDATE projects SET marketplace_status = 'awarded', awarded_bid_id = %s WHERE id = %s;",
            (bid_id, project_id),
        )
        conn.commit()
    return bid


def close_bidding_without_award(project_id: UUID) -> dict[str, Any] | None:
    """Close bidding on a project without awarding anyone; declines every
    outstanding submitted bid so none are left stranded in 'submitted' on a
    project that's no longer accepting decisions."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE bids SET status = 'declined', decided_at = now() WHERE project_id = %s AND status = 'submitted';",
            (project_id,),
        )
        row = conn.execute(
            "UPDATE projects SET marketplace_status = 'closed' WHERE id = %s RETURNING *;",
            (project_id,),
        ).fetchone()
        conn.commit()
    return row

