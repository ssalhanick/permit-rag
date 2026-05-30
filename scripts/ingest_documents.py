"""
scripts/ingest_documents.py — Ingest 10 passing docs into the database
======================================================================
Chunks each document and inserts both the document row (via insert_document)
and its chunks (via insert_chunks) into the database.

Skips the 3 Municode redirect pages that fail extraction.

Run from project root:
    py -m scripts.ingest_documents
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# The 3 Municode redirect pages that fail extraction (<100 chars)
SKIP_DOC_IDS = {
    "frisco-municode-zoning",
    "mckinney-municode-zoning",
    "plano-municode-zoning",
}


def get_catalog_entry(doc_id: str) -> dict | None:
    """Look up a doc_id in the harvester catalog."""
    from ingestion.harvester import DOCUMENT_CATALOG

    for entry in DOCUMENT_CATALOG:
        if entry["doc_id"] == doc_id:
            return entry
    return None


def ingest_all(*, new_only: bool = True):
    """Ingest passing documents into the database."""
    from db.client import (
        close_pool,
        get_document_by_doc_id,
        insert_chunks,
        insert_document,
        ping,
    )
    from ingestion.chunker import chunk_document
    from ingestion.verification import (
        run_full_verification,
        save_verification_to_db,
    )

    # 1. Verify DB connection
    if not ping():
        log.error("Cannot connect to database. Is Docker running?")
        sys.exit(1)
    log.info("Database connection OK")

    # 2. Discover documents in raw/
    raw_dir = Path("documents/raw")
    if not raw_dir.exists():
        log.error("documents/raw/ not found")
        sys.exit(1)

    files = sorted(raw_dir.iterdir())
    all_doc_ids = [f.stem for f in files if f.is_file()]
    doc_ids = [d for d in all_doc_ids if d not in SKIP_DOC_IDS]
    log.info(
        "Found %d documents total, %d passing (skipping %d Municode redirects)",
        len(all_doc_ids), len(doc_ids), len(SKIP_DOC_IDS),
    )

    results = {"success": [], "fail": [], "skipped_existing": []}

    for doc_id in doc_ids:
        log.info("\n" + "=" * 60)
        log.info("Ingesting: %s", doc_id)

        if new_only and get_document_by_doc_id(doc_id):
            log.info("Skipping existing document (new-only mode): %s", doc_id)
            results["skipped_existing"].append(doc_id)
            continue

        # ── Step 1: Chunk the document ──────────────────────────
        try:
            chunk_result = chunk_document(doc_id, raw_dir=raw_dir)
        except Exception as exc:
            log.error("Chunker failed for %s: %s", doc_id, exc)
            results["fail"].append({"doc_id": doc_id, "error": str(exc)})
            continue

        # ── Step 2: Verify (download + extraction + chunking) ───
        vresults = run_full_verification(
            doc_id=doc_id,
            raw_path=chunk_result["raw_path"],
            raw_chars=chunk_result["raw_chars"],
            clean_chars=chunk_result["clean_chars"],
            chunks=chunk_result["chunks"],
            is_scanned=chunk_result["is_scanned"],
            save_to_db=False,  # save after document insert
        )
        final = vresults[-1] if vresults else None
        if not final or not final.passed:
            log.error("Verification failed for %s — skipping", doc_id)
            results["fail"].append({
                "doc_id": doc_id,
                "error": f"Verification failed at {final.stage}: {final.result}"
                if final else "no results",
            })
            continue

        # ── Step 3: Insert document row ─────────────────────────
        catalog = get_catalog_entry(doc_id)
        if not catalog:
            log.error("No catalog entry for %s — skipping", doc_id)
            results["fail"].append({"doc_id": doc_id, "error": "not in catalog"})
            continue

        review_days = catalog.get("review_days", 90)
        review_due = date.today() + timedelta(days=review_days)

        doc_row = insert_document(
            doc_id=doc_id,
            source_url=catalog["url"],
            municipality=catalog["municipality"],
            authority_level=catalog["authority_level"],
            doc_type=catalog["doc_type"],
            subject_tags=catalog.get("subject_tags", []),
            effective_date=None,
            document_status="active",
            is_current=True,
            retrieval_weight=1.0,
            review_due=review_due,
            local_path=str(chunk_result["raw_path"]),
        )
        document_uuid = doc_row["id"]
        log.info("Inserted document: %s → %s", doc_id, document_uuid)

        # ── Step 4: Insert chunks ───────────────────────────────
        num_inserted = insert_chunks(document_uuid, chunk_result["chunks"])
        log.info("Inserted %d chunks for %s", num_inserted, doc_id)

        # ── Step 5: Save verifications to DB ────────────────────
        for v in vresults:
            save_verification_to_db(v, document_uuid)

        results["success"].append({
            "doc_id": doc_id,
            "document_id": str(document_uuid),
            "num_chunks": num_inserted,
        })

        print(f"  ✅ {doc_id}: {num_inserted} chunks")

    # ── Summary ─────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print("  INGESTION SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Succeeded: {len(results['success'])}")
    print(f"  Skipped existing: {len(results['skipped_existing'])}")
    print(f"  Failed:    {len(results['fail'])}")

    total_chunks = sum(r["num_chunks"] for r in results["success"])
    print(f"  Total chunks in DB: {total_chunks:,}")

    if results["fail"]:
        print("\n  Failures:")
        for f in results["fail"]:
            print(f"    ❌ {f['doc_id']}: {f['error']}")

    print(f"{'=' * 60}\n")

    close_pool()
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest documents into DB (new-only by default)"
    )
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Re-ingest existing doc_ids (default: skip existing)",
    )
    args = parser.parse_args()

    ingest_all(new_only=not args.include_existing)
