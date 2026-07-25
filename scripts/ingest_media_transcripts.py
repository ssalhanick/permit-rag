"""
scripts/ingest_media_transcripts.py — ingest vetted-video transcripts (Slice C1).

Walks the curated ``media_refs`` table, fetches each video's transcript, and
stores it as a **segregated, non-authoritative** document (`content_class='how_to'`,
`doc_type='how_to_video'`, `authority_level='educational'`, `source_tier=3`) so a
DIY how-to query can be grounded on how-to content **without** letting video text
ground or cite a compliance answer (migration 031 + the match_chunks filter).

Reuses the corpus pipeline: ``ingestion.chunker.split_text`` → ``db.client``
insert → ``ingestion.embedder.embed_document`` (local nomic, no API cost).

Target-safe via scripts/_db_target. Dry-run by default; ``--apply`` writes.
Local→prod is the same pattern as ingest_prod_corpus: run under
``ENVIRONMENT=production`` (or ``--database-url``) to push transcript docs to RDS.

    py scripts/ingest_media_transcripts.py --local              # dry-run
    py scripts/ingest_media_transcripts.py --local --apply      # chunk + embed + store
    ENVIRONMENT=production py scripts/ingest_media_transcripts.py --apply   # push to prod

Prereq: migration 031 applied; media_refs seeded with vetted links.
Metadata-policy note (AGENTS.md "never ingest without full metadata"): transcripts
are an explicit exception — effective_date/review_due are NULL by design (a video
has no adoption date) and authority_level='educational' records that it is not a
government source.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest media_refs video transcripts.")
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--apply", action="store_true", help="Write (default: dry-run).")
    parser.add_argument("--force", action="store_true", help="Re-embed even if chunks exist.")
    return parser.parse_args(argv)


def _doc_id_for(video_id: str) -> str:
    return f"how-to-{video_id}"


def _ingest_one(ref: dict, *, apply: bool, force: bool) -> str:
    """Ingest a single media_ref transcript. Returns a status word for the report."""
    from ingestion.chunker import split_text
    from ingestion.transcript import fetch_transcript, video_id_from_url

    url = ref["url"]
    vid = video_id_from_url(url)
    if vid is None:
        return "skipped (not a youtube video url)"

    transcript = fetch_transcript(url)
    if not transcript:
        return "skipped (no transcript)"

    chunks = split_text(transcript)
    if not chunks:
        return "skipped (empty after chunking)"

    if not apply:
        return f"would ingest — {len(transcript)} chars, {len(chunks)} chunks"

    from db.client import insert_chunks, insert_document
    from ingestion.embedder import embed_document

    doc_id = _doc_id_for(vid)
    doc = insert_document(
        doc_id=doc_id,
        source_url=url,
        municipality=(ref.get("jurisdiction") or "national"),
        authority_level="educational",
        doc_type="how_to_video",
        subject_tags=[ref["task_key"]],
        effective_date=None,
        checksum_sha256=hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        source_tier=3,
        content_class="how_to",
    )
    insert_chunks(doc["id"], chunks)
    try:
        result = embed_document(doc_id, force=force)
        return f"ingested — {result.get('num_chunks', len(chunks))} chunks embedded"
    except Exception as exc:  # embedding is heavy/local; report but do not abort the run
        return f"ingested chunks, EMBED FAILED ({exc})"


def main(argv: list[str] | None = None) -> int:
    """Resolve the target, then dry-run or ingest every media_ref transcript."""
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not args.apply)
    _db_target.ensure_reachable(target)

    from db.client import list_media_refs

    refs = list_media_refs(active_only=True)
    print(f"\n{len(refs)} active media_refs to process (apply={args.apply}):\n")
    counts: dict[str, int] = {"ingested": 0, "skipped": 0}
    for ref in refs:
        status = _ingest_one(ref, apply=args.apply, force=args.force)
        bucket = "skipped" if status.startswith("skipped") else "ingested"
        counts[bucket] += 1
        print(f"  [{bucket}] {ref['task_key']:28} {ref['url']}\n           {status}")

    print(f"\nDone. {counts['ingested']} processed, {counts['skipped']} skipped.")
    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply to ingest.")
    else:
        print("⚠ match_chunks changed by migration 031 — run RAGAs to confirm compliance "
              "retrieval is unchanged (default filter is authority-only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
