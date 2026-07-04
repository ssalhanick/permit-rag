"""
scripts/ingest_prod_corpus.py — Seed production RDS with the local document corpus
==================================================================================
Run from project root after filling `.env.production` with RDS credentials.

Budget (local snapshot): ~10 docs, ~7,170 chunks, local nomic embeddings (no API cost).

Usage:
    $env:ENVIRONMENT="production"
    py scripts/ingest_prod_corpus.py

    # Skip harvest when documents/raw/ already has all files:
    py scripts/ingest_prod_corpus.py --skip-harvest

Steps: verify RDS connectivity → [harvest] → ingest → embed → verify counts.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.load_env import bootstrap_env

bootstrap_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

EXPECTED_DOCS = 10
EXPECTED_CHUNKS_MIN = 7000


def _require_production() -> None:
    """Abort unless ENVIRONMENT=production and DATABASE_URL is not localhost."""
    env = os.environ.get("ENVIRONMENT", "")
    db_url = os.environ.get("DATABASE_URL", "")
    if env != "production":
        log.error('Set ENVIRONMENT=production before running this script.')
        sys.exit(1)
    if not db_url or "localhost" in db_url or "127.0.0.1" in db_url:
        log.error("DATABASE_URL must point at production RDS (see .env.production).")
        sys.exit(1)


def _verify_counts() -> None:
    """Print document and embedded-chunk counts from RDS."""
    from db.client import get_conn

    with get_conn() as conn:
        doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE document_status = 'active'").fetchone()[0]
        chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        embedded = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()[0]
    log.info("RDS corpus: %s active docs, %s chunks (%s embedded)", doc_count, chunk_count, embedded)
    if doc_count < 1:
        log.warning("No active documents in RDS — ingestion may have failed.")
    if embedded < EXPECTED_CHUNKS_MIN:
        log.warning(
            "Embedded chunk count %s is below expected minimum %s.",
            embedded,
            EXPECTED_CHUNKS_MIN,
        )


def main() -> None:
    """Run optional harvest → ingest → embed against production RDS."""
    parser = argparse.ArgumentParser(description="Seed production RDS from documents/raw/")
    parser.add_argument(
        "--skip-harvest",
        action="store_true",
        help="Skip harvester; ingest files already in documents/raw/ (catalog.json still required)",
    )
    args = parser.parse_args()

    _require_production()
    log.info("=== Production corpus ingest (P0-2) ===")
    log.info("Expected: ~%s docs, ~%s+ chunks (local nomic embed, no LLM cost)", EXPECTED_DOCS, EXPECTED_CHUNKS_MIN)
    if args.skip_harvest:
        log.info("Harvest skipped — using existing files in documents/raw/")

    confirm = input("Proceed with RDS corpus ingest? (yes/no): ").strip().lower()
    if confirm != "yes":
        log.info("Aborted.")
        return

    step = 1
    total = 3 if args.skip_harvest else 4

    if not args.skip_harvest:
        log.info("[%s/%s] Harvesting documents (reuses local raw files when present)...", step, total)
        from ingestion.harvester import harvest

        harvest()
        step += 1

    log.info("[%s/%s] Ingesting documents + chunks into RDS...", step, total)
    from scripts.ingest_documents import ingest_all

    ingest_all(new_only=False)
    step += 1

    log.info("[%s/%s] Embedding chunks (local model — may take several minutes)...", step, total)
    from ingestion.embedder import embed_all_documents

    embed_all_documents(force=False)

    log.info("Verifying RDS counts...")
    _verify_counts()
    log.info("Done. Smoke test: GET https://permits.scottsalhanick.com/documents (should not be []).")


if __name__ == "__main__":
    main()
