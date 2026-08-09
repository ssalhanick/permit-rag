"""
scripts/reconcile_stuck_uploads.py — Find/retry abandoned background uploads
==============================================================================
_process_upload (api/routes/upload.py) runs as an in-process FastAPI
BackgroundTasks callback with no durable job queue behind it. If the
container is killed or restarts mid-job, the task simply vanishes: no
exception handler ever runs, so the document is left at document_status
='draft' forever, indistinguishable in the DB from a legitimate pending-
review petition (tier-2 ordinance petitions and tier-3 overlay petitions are
both scheduled with auto_activate=False and correctly stay 'draft' while
awaiting admin review).

The distinguishing signal: chunking happens *before* the auto_activate gate,
so a legitimately-pending petition always has chunks by the time it's sitting
at 'draft'. A 'draft' document with zero chunks, past a grace period, is
either an abandoned background job or an ordinary processing failure that
never got its needs_ocr/draft failure status recorded -- either way nothing
else in this system will ever surface it to a human.

This is a lightweight, manually/cron-invoked reconciliation script, not a
job queue -- appropriate for the current MVP contributor scale. If petition
volume grows enough that this needs to run continuously rather than as a
periodic check, that's the point to build real job-queue infrastructure
(e.g. a Postgres job table with retry semantics, or SQS + a worker) instead
of scaling this script further.

Usage (from project root):
    python -m scripts.reconcile_stuck_uploads                     # report only
    python -m scripts.reconcile_stuck_uploads --min-age-minutes 60
    python -m scripts.reconcile_stuck_uploads --retry              # re-process
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.load_env import bootstrap_env

bootstrap_env()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _report(rows: list[dict]) -> None:
    print(f"\n{'=' * 70}")
    print(f"  STUCK/FAILED UPLOAD CANDIDATES: {len(rows)}")
    print(f"{'=' * 70}")
    for row in rows:
        print(
            f"  doc_id={row['doc_id']!r} municipality={row['municipality']!r} "
            f"source_tier={row['source_tier']} uploaded_by={row.get('uploaded_by')} "
            f"ingested_at={row['ingested_at']} overlay_id={row.get('overlay_id')}"
        )
    print(f"{'=' * 70}\n")


def _retry(rows: list[dict]) -> None:
    from api.routes.upload import _process_upload

    for row in rows:
        # tier-2 ordinance petitions and any overlay-linked document must stay
        # 'draft' (pending admin review) on success -- only auto-activate the
        # cases that were never meant to be gated by a review queue.
        auto_activate = row["source_tier"] != 2 and row.get("overlay_id") is None
        log.info("Retrying doc_id=%s (auto_activate=%s)", row["doc_id"], auto_activate)
        try:
            _process_upload(
                doc_id=row["doc_id"],
                local_path=row["local_path"],
                source_url=row["source_url"],
                municipality=row["municipality"],
                authority_level=row["authority_level"],
                doc_type=row["doc_type"],
                subject_tags=row["subject_tags"],
                source_tier=row["source_tier"],
                project_id=row.get("project_id"),
                uploaded_by=row.get("uploaded_by"),
                overlay_id=row.get("overlay_id"),
                visibility=row.get("visibility") or "team",
                auto_activate=auto_activate,
            )
        except Exception:
            # _process_upload already catches and records its own failures
            # (needs_ocr/draft); this guards the script loop against a
            # completely unexpected error (e.g. the row's local_path is gone)
            # so one bad row doesn't stop the rest from being retried.
            log.exception("Retry failed unexpectedly for doc_id=%s", row["doc_id"])


def main() -> None:
    from db.client import get_stuck_draft_documents

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-age-minutes", type=int, default=30,
        help="Only flag drafts older than this (default: 30). Should comfortably "
             "exceed how long a normal chunk+embed job takes.",
    )
    parser.add_argument(
        "--retry", action="store_true",
        help="Re-run chunk+embed for each flagged document instead of just reporting.",
    )
    args = parser.parse_args()

    rows = get_stuck_draft_documents(min_age_minutes=args.min_age_minutes)
    _report(rows)
    if args.retry and rows:
        _retry(rows)


if __name__ == "__main__":
    main()
