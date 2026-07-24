"""
scripts/backfill_source_identity.py — One-off backfill for migration 022
=========================================================================
Populates documents.source_url_normalized and documents.source_filename
from existing source_url / local_path using the shared normalizer
(ingestion/url_normalize.py).

Requires migration 022 to be applied to the target database: it adds the
columns this script fills. Without it the queries below fail on an undefined
column, which is checked for up front so the failure names the cause.

Usage:
    py scripts/backfill_source_identity.py
    py scripts/backfill_source_identity.py --local
    py scripts/backfill_source_identity.py --database-url='postgresql://...'

Idempotent: only touches rows where either key is NULL.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

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


def require_migration_022(conn) -> None:
    """
    Exit with a named cause when 022's columns are absent.

    Without this the script dies on `psycopg.errors.UndefinedColumn:
    source_url_normalized`, which says what broke but not why or on which
    database -- and the target is easy to get wrong, since `.env` overrides
    `.env.local` and both are gitignored.
    """
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name='documents' AND column_name='source_url_normalized') "
        "AS present;"
    ).fetchone()
    if row and row["present"]:
        return

    print(f"\nMigration 022 is not applied to {TARGET.host}.")
    print(f"  source: {TARGET.source}")
    print("\n  This script fills columns that 022 adds, so there is nothing to")
    print("  backfill until it runs. Apply it:")
    print("    py scripts/apply_migration.py db/migrations/022_source_identity.sql")
    print("\n  If that host is not the database you meant, re-run with --local")
    print("  or --database-url=. To see every database's state:")
    print("    py scripts/check_migrations.py --local")
    sys.exit(1)


def main() -> None:
    """Backfill identity keys for all documents missing them."""
    _db_target.banner(TARGET, read_only=False)
    _db_target.ensure_reachable(TARGET)

    with get_conn() as conn:
        require_migration_022(conn)
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
