"""
scripts/backfill_document_metadata.py — one-time corpus metadata backfill
=========================================================================
Phase 3. Runs the Corpus Metadata Validator (agent #13) over every document in
the corpus and reports what it would fix: null effective_dates, catch-all
doc_types, empty subject_tags, and supersession families
(city-of-dallas-ordiance-v1/v2/v3).

**Machine B only.** This needs the real corpus and its chunks; on the repo
machine (empty DB, no documents/raw/) there is nothing to validate. It also
makes a priced LLM call per document unless ``--no-llm`` is passed
(~$0.48-$0.95 for the 27-doc corpus, one-time).

Governance (AGENTS.md): the backfill NEVER writes corrected metadata and NEVER
drafts a live document — drafting all 27 currently-null-effective_date docs
would empty retrieval. It only files ``needs_review`` action items (with
``--apply``); a superadmin approves each in the dashboard, and only then does
``ingestion.governance.apply_metadata_correction`` write.

Usage:
    py scripts/backfill_document_metadata.py --local --dry-run --report
    py scripts/backfill_document_metadata.py --local --apply        # file items
    py scripts/backfill_document_metadata.py --local --no-llm --report
    py scripts/backfill_document_metadata.py --database-url='<url>' --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI flags. --apply is the only thing that writes anything."""
    parser = argparse.ArgumentParser(description="Corpus metadata backfill (validator).")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate + report only; file nothing (default behaviour).")
    parser.add_argument("--apply", action="store_true",
                        help="File needs_review action items (still no corpus writes).")
    parser.add_argument("--no-llm", action="store_true",
                        help="Deterministic checks only; skip the priced LLM call.")
    parser.add_argument("--report", action="store_true", help="Print the per-doc report.")
    parser.add_argument("--doc-id", action="append", dest="doc_ids",
                        help="Limit to specific doc_id(s); repeatable.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, run the validator over the corpus, print a report."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    apply = args.apply and not args.dry_run

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not apply)
    _db_target.ensure_reachable(target)

    # Import after the target is fixed so db.client binds to the right DSN.
    from ingestion.metadata_agent import validate_corpus

    print(f"Running metadata validator (llm={'off' if args.no_llm else 'on'}, "
          f"apply={apply}) ...\n")
    reports = validate_corpus(
        doc_ids=args.doc_ids,
        use_llm=not args.no_llm,
        file_action_items=apply,
        save_verification=apply,
    )

    _print_summary(reports)
    if args.report:
        _print_detail(reports)
    if not apply:
        print("\nDry run — no action items filed. Re-run with --apply to file them.")
    return 0


def _print_summary(reports: list) -> None:
    """Roll up counts across the corpus."""
    total = len(reports)
    by_result: dict[str, int] = {}
    null_dates = catchall = empty_tags = enum_bad = families = proposals = 0
    for r in reports:
        by_result[r.result] = by_result.get(r.result, 0) + 1
        if "effective_date" in r.completeness_failures:
            null_dates += 1
        if "subject_tags" in r.completeness_failures:
            empty_tags += 1
        if r.enum_failures:
            enum_bad += 1
        if r.supersession_candidates:
            families += 1
        proposals += len(r.proposals)
        if any(p.field == "doc_type" and p.current in (None, "", "other") for p in r.proposals):
            catchall += 1

    print("=" * 60)
    print(f"  Documents validated : {total}")
    print(f"  Results             : {by_result}")
    print(f"  Null effective_date : {null_dates}")
    print(f"  Empty subject_tags  : {empty_tags}")
    print(f"  Catch-all doc_type replacements proposed : {catchall}")
    print(f"  Invalid enum value  : {enum_bad}")
    print(f"  Supersession families flagged : {families}")
    print(f"  Total proposals (with citations): {proposals}")
    print("=" * 60)


def _print_detail(reports: list) -> None:
    """Per-document lines: result, failures, and cited proposals."""
    print("\nPer-document detail")
    print("-" * 60)
    for r in reports:
        icon = {"pass": "✅", "needs_review": "📝", "fail": "❌"}.get(r.result, "❓")
        print(f"{icon} {r.doc_id}  [{r.result}]")
        if r.enum_failures:
            print(f"    enum: {'; '.join(r.enum_failures)}")
        if r.completeness_failures:
            print(f"    missing: {', '.join(r.completeness_failures)}")
        for p in r.proposals:
            cite = p.citation
            where = f"chunk {cite.chunk_index}" if cite.chunk_index is not None else "no citation"
            print(f"    → {p.field}: {p.current!r} ⇒ {p.proposed!r} "
                  f"(conf={p.confidence:.2f}, {where})")
        if r.supersession_candidates:
            print(f"    supersession family: {', '.join(r.supersession_candidates)}")


if __name__ == "__main__":
    raise SystemExit(main())
