"""
scripts/run_chunk_verify.py — Schema check + chunk + verify all 13 docs
======================================================================
Run from project root:
    py -m scripts.run_chunk_verify
"""

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def check_schema():
    """Verify that all expected tables exist in the database."""
    from db.client import get_conn

    expected = {"documents", "chunks", "ingestion_verifications", "query_log"}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
    found = {r["tablename"] for r in rows}
    missing = expected - found
    if missing:
        log.error("Missing tables: %s", missing)
        sys.exit(1)
    log.info("Schema OK — tables: %s", sorted(found))
    return found


def run_chunker_and_verify():
    """Run chunker + verification for every file in documents/raw/."""
    from ingestion.chunker import chunk_document
    from ingestion.verification import (
        print_verification_summary,
        run_full_verification,
    )

    raw_dir = Path("documents/raw")
    if not raw_dir.exists():
        log.error("documents/raw/ not found")
        sys.exit(1)

    # Collect all doc_ids from filenames
    files = sorted(raw_dir.iterdir())
    doc_ids = [f.stem for f in files if f.is_file()]
    log.info("Found %d documents in %s", len(doc_ids), raw_dir)

    all_results = []
    summary = {"pass": 0, "fail": 0, "needs_ocr": 0, "skip": 0}

    for doc_id in doc_ids:
        log.info("\n{'='*60}")
        log.info("Processing: %s", doc_id)

        try:
            result = chunk_document(doc_id, raw_dir=raw_dir)
        except Exception as exc:
            log.error("Chunker failed for %s: %s", doc_id, exc)
            summary["fail"] += 1
            continue

        # Run verification (download + extraction + chunking)
        vresults = run_full_verification(
            doc_id=doc_id,
            raw_path=result["raw_path"],
            raw_chars=result["raw_chars"],
            clean_chars=result["clean_chars"],
            chunks=result["chunks"],
            is_scanned=result["is_scanned"],
            save_to_db=False,  # DB ingestion comes after embedder
        )

        all_results.extend(vresults)

        # Track outcome (last verification stage is the final verdict)
        final = vresults[-1] if vresults else None
        if final:
            summary[final.result] = summary.get(final.result, 0) + 1

        # Print per-doc summary
        print(f"\n  {doc_id}:")
        print(f"    raw_chars  : {result['raw_chars']:,}")
        print(f"    clean_chars: {result['clean_chars']:,}")
        print(f"    num_chunks : {result['num_chunks']}")
        print(f"    is_scanned : {result['is_scanned']}")
        for v in vresults:
            icon = {"pass": "✅", "fail": "❌", "needs_ocr": "🔍"}.get(
                v.result, "❓"
            )
            print(f"    {icon} {v.stage}: {v.result}")
            if "error" in v.detail:
                print(f"       └─ {v.detail['error']}")

    # Final summary
    print(f"\n{'='*60}")
    print("  CHUNK + VERIFY SUMMARY")
    print(f"{'='*60}")
    print(f"  Documents processed: {len(doc_ids)}")
    print(f"  All stages passed  : {summary.get('pass', 0)}")
    print(f"  Failed             : {summary.get('fail', 0)}")
    print(f"  Needs OCR          : {summary.get('needs_ocr', 0)}")
    print(f"{'='*60}\n")

    return all_results


if __name__ == "__main__":
    log.info("Step 1: Checking database schema...")
    check_schema()

    log.info("\nStep 2: Running chunker + verification on all documents...")
    run_chunker_and_verify()

    log.info("Done.")
