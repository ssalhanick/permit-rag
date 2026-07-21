"""
scripts/backfill_source_identity.py — One-off backfill for migration 022
=========================================================================
Populates documents.source_url_normalized and documents.source_filename
from existing source_url / local_path using the shared normalizer
(ingestion/url_normalize.py).

Usage:
    py scripts/backfill_source_identity.py            # local
    $env:ENVIRONMENT="production"; py scripts/backfill_source_identity.py

Idempotent: only touches rows where either key is NULL.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.load_env import bootstrap_env

bootstrap_env()

from db.client import get_conn
from ingestion.url_normalize import normalize_filename, normalize_source_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill_source_identity")


def _identity_keys(source_url: str | None, local_path: str | None) -> tuple[str | None, str | None]:
    """Compute (source_url_normalized, source_filename) for one document row."""
    url_norm: str | None = None
    if source_url and not source_url.startswith("file://"):
        # Repair known data typo: leading slash(es) before the scheme
        candidate = source_url.lstrip("/") if source_url.lstrip("/").startswith("http") else source_url
        try:
            url_norm = normalize_source_url(candidate)
        except ValueError:
            log.warning("Cannot normalize source_url %r — leaving NULL", source_url)

    filename_src = local_path or source_url or ""
    filename = normalize_filename(filename_src) if filename_src else None
    return url_norm, filename or None


def main() -> None:
    """Backfill identity keys for all documents missing them."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, doc_id, source_url, local_path
            FROM documents
            WHERE source_url_normalized IS NULL OR source_filename IS NULL
            ORDER BY doc_id;
            """
        ).fetchall()

        log.info("Backfilling %d documents", len(rows))
        updated = 0
        for row in rows:
            url_norm, filename = _identity_keys(row["source_url"], row["local_path"])
            conn.execute(
                """
                UPDATE documents
                SET source_url_normalized = COALESCE(source_url_normalized, %s),
                    source_filename       = COALESCE(source_filename, %s)
                WHERE id = %s;
                """,
                (url_norm, filename, row["id"]),
            )
            updated += 1
            log.info("  %s  url_norm=%s  filename=%s", row["doc_id"], url_norm, filename)

        conn.commit()

        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE source_url_normalized IS NULL;"
        ).fetchone()
        log.info(
            "Done. Updated %d rows. %d rows still have NULL source_url_normalized "
            "(file:// or unparseable — fallback identity will be used).",
            updated,
            remaining["n"],
        )


if __name__ == "__main__":
    main()
