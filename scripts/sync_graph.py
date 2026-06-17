"""
scripts/sync_graph.py — Bulk-sync Postgres corpus into Neo4j
=============================================================
Walks the active documents and their chunks in Postgres and upserts
each one into Neo4j via db.graph_client.

Run after initial ingest or whenever the corpus changes:
    py -m scripts.sync_graph [--dry-run] [--municipality MUNI] [--doc-id DOC_ID]

Import boundary: scripts/ → may import anything (AGENTS.md one-off use).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Optional

# Load .env before any db/ imports so DATABASE_URL and NEO4J_* are available.
# Falls back silently when python-dotenv is not installed (env already set by shell).
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass

log = logging.getLogger("scripts.sync_graph")

# ── Logging setup ────────────────────────────────────────────


def _setup_logging(verbose: bool) -> None:
    """Configure root logging for the sync run."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stdout,
    )


# ── Sync helpers ─────────────────────────────────────────────


def _sync_document(doc: dict, *, dry_run: bool) -> int:
    """
    Upsert one Document node (+ Municipality + AuthorityLevel + edges).

    Returns the number of chunks synced for this document.
    """
    from db.client import get_chunks_for_document
    from db.graph_client import upsert_chunk_node, upsert_document_node

    doc_id = doc["doc_id"]
    pg_id = str(doc["id"])

    if not dry_run:
        upsert_document_node(
            doc_id=doc_id,
            pg_id=pg_id,
            municipality=doc.get("municipality", "unknown"),
            authority_level=doc.get("authority_level", "municipal"),
            doc_type=doc.get("doc_type", "other"),
            document_status=doc.get("document_status", "active"),
            source_tier=int(doc.get("source_tier", 1)),
            retrieval_weight=float(doc.get("retrieval_weight", 1.0)),
            source_url=doc.get("source_url", ""),
        )
    else:
        log.info("[dry-run] Would upsert Document: %s", doc_id)

    chunks = get_chunks_for_document(doc["id"])
    for chunk in chunks:
        if not dry_run:
            upsert_chunk_node(
                pg_id=str(chunk["id"]),
                doc_id=doc_id,
                chunk_index=int(chunk["chunk_index"]),
                content=chunk.get("content", ""),
                municipality=doc.get("municipality", "unknown"),
                authority_level=doc.get("authority_level", "municipal"),
            )
        else:
            log.debug(
                "[dry-run] Would upsert Chunk: %s[%d]",
                doc_id, chunk["chunk_index"],
            )

    return len(chunks)


def _sync_supersessions(docs: list[dict], *, dry_run: bool) -> int:
    """
    Link SUPERSEDED_BY edges for documents that have superseded_by set.

    Returns the number of edges created/merged.
    """
    from db.client import get_document_by_uuid
    from db.graph_client import link_supersession

    edges = 0
    for doc in docs:
        if not doc.get("superseded_by"):
            continue
        replacement = get_document_by_uuid(doc["superseded_by"])
        if replacement is None:
            log.warning("superseded_by UUID %s not found for %s", doc["superseded_by"], doc["doc_id"])
            continue
        if not dry_run:
            link_supersession(doc["doc_id"], replacement["doc_id"])
        else:
            log.info(
                "[dry-run] Would link SUPERSEDED_BY: %s → %s",
                doc["doc_id"], replacement["doc_id"],
            )
        edges += 1

    return edges


# ── Main ─────────────────────────────────────────────────────


def main(
    *,
    dry_run: bool = False,
    municipality: Optional[str] = None,
    doc_id_filter: Optional[str] = None,
    verbose: bool = False,
) -> None:
    """
    Sync the Postgres permit corpus into Neo4j.

    Reads all active documents (optionally filtered), upserts Document and
    Chunk nodes, then creates SUPERSEDED_BY edges where applicable.

    Args:
        dry_run: Log what would be done without touching Neo4j.
        municipality: Only sync documents for this municipality.
        doc_id_filter: Only sync this single doc_id.
        verbose: Enable DEBUG logging.
    """
    _setup_logging(verbose)
    t0 = time.perf_counter()

    from db.client import list_documents
    from db.graph_client import apply_constraints, ping

    # Validate Neo4j reachable
    if not dry_run:
        if not ping():
            log.error("Neo4j is not reachable. Is the container running?")
            sys.exit(1)
        log.info("Neo4j reachable — applying constraints (idempotent)")
        apply_constraints()

    # Load documents from Postgres
    filters: dict = {}
    if municipality:
        filters["municipality"] = municipality
    docs = list_documents(**filters)

    if doc_id_filter:
        docs = [d for d in docs if d["doc_id"] == doc_id_filter]
        if not docs:
            log.error("doc_id not found: %s", doc_id_filter)
            sys.exit(1)

    log.info(
        "Syncing %d document(s)%s%s",
        len(docs),
        f" (municipality={municipality})" if municipality else "",
        f" (doc_id={doc_id_filter})" if doc_id_filter else "",
    )

    total_chunks = 0
    for i, doc in enumerate(docs, 1):
        chunk_count = _sync_document(doc, dry_run=dry_run)
        total_chunks += chunk_count
        log.info(
            "[%d/%d] %s — %d chunk(s)",
            i, len(docs), doc["doc_id"], chunk_count,
        )

    edges = _sync_supersessions(docs, dry_run=dry_run)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    log.info(
        "Sync complete: %d doc(s), %d chunk node(s), %d supersession edge(s) in %dms%s",
        len(docs),
        total_chunks,
        edges,
        elapsed_ms,
        " [DRY RUN]" if dry_run else "",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bulk-sync Postgres permit corpus into Neo4j."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be synced without touching Neo4j.",
    )
    parser.add_argument(
        "--municipality",
        default=None,
        help="Filter to a single municipality (e.g. dallas).",
    )
    parser.add_argument(
        "--doc-id",
        dest="doc_id",
        default=None,
        help="Sync only this specific doc_id.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    args = parser.parse_args()
    main(
        dry_run=args.dry_run,
        municipality=args.municipality,
        doc_id_filter=args.doc_id,
        verbose=args.verbose,
    )
