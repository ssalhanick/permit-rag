"""
scripts/sync_how_to_to_prod.py — copy already-ingested how-to media data to prod.

When transcripts were ingested + embedded on a LOCAL db (e.g. from a residential
IP), this copies the finished rows straight to the target (prod RDS) — no YouTube
fetch, no re-embed, so it sidesteps IP blocks entirely. Copies, in order:

    media_channels  →  media_refs  →  how_to documents  →  their chunks (+vectors)

Read side: ``--source-url`` (the local db). Write side: target-safe via
scripts/_db_target (ENVIRONMENT=production, --database-url, or --local for a test),
with the remote-confirm banner. Dry-run by default; --apply writes. Idempotent —
upserts on natural keys, re-copies a document's chunks cleanly.

    py scripts/sync_how_to_to_prod.py --source-url postgresql://... --apply   # → prod (ENVIRONMENT=production)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import psycopg
from psycopg.rows import dict_row

import _db_target

from api.load_env import bootstrap_env


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Copy how-to media data from a source db to the target.")
    p.add_argument("--source-url", required=True, help="Source DATABASE_URL to read from (e.g. local).")
    p.add_argument("--local", action="store_true", help="Target = .env.local (test).")
    p.add_argument("--database-url", help="Explicit TARGET DATABASE_URL (bypasses dotenv).")
    p.add_argument("--apply", action="store_true", help="Write to the target (default: dry-run).")
    return p.parse_args(argv)


def _sync_media_channels(src: Any, tgt: Any, apply: bool) -> int:
    rows = src.execute("SELECT * FROM media_channels;").fetchall()
    if apply:
        for r in rows:
            tgt.execute(
                """INSERT INTO media_channels (channel_id, name, provider, jurisdiction, vetted_by, active)
                   VALUES (%(channel_id)s,%(name)s,%(provider)s,%(jurisdiction)s,%(vetted_by)s,%(active)s)
                   ON CONFLICT (channel_id) DO UPDATE SET
                     name=EXCLUDED.name, jurisdiction=EXCLUDED.jurisdiction,
                     vetted_by=EXCLUDED.vetted_by, active=EXCLUDED.active;""",
                r,
            )
    return len(rows)


def _sync_media_refs(src: Any, tgt: Any, apply: bool) -> int:
    rows = src.execute("SELECT * FROM media_refs;").fetchall()
    if apply:
        for r in rows:
            tgt.execute(
                """INSERT INTO media_refs
                     (task_key, title, url, provider, jurisdiction, relevance_note,
                      last_verified_at, active, channel_id)
                   VALUES (%(task_key)s,%(title)s,%(url)s,%(provider)s,%(jurisdiction)s,
                           %(relevance_note)s,%(last_verified_at)s,%(active)s,%(channel_id)s)
                   ON CONFLICT (task_key, url) DO UPDATE SET
                     title=EXCLUDED.title, relevance_note=EXCLUDED.relevance_note,
                     last_verified_at=EXCLUDED.last_verified_at, active=EXCLUDED.active,
                     channel_id=EXCLUDED.channel_id;""",
                r,
            )
    return len(rows)


_DOC_COLS = (
    "doc_id, source_url, municipality, authority_level, doc_type, subject_tags, "
    "effective_date, document_status, is_current, retrieval_weight, review_due, "
    "checksum_sha256, source_etag, local_path, source_tier, content_class"
)


def _sync_documents_and_chunks(src: Any, tgt: Any, apply: bool) -> tuple[int, int]:
    docs = src.execute(
        f"SELECT id, {_DOC_COLS} FROM documents WHERE content_class = 'how_to';"
    ).fetchall()
    n_chunks = 0
    for d in docs:
        src_id = d["id"]
        chunks = src.execute(
            """SELECT chunk_index, content, char_count, page_start, page_end,
                      content_hash, status, embedding::text AS emb
               FROM chunks WHERE document_id = %s ORDER BY chunk_index;""",
            (src_id,),
        ).fetchall()
        n_chunks += len(chunks)
        if not apply:
            continue
        # Upsert the document by doc_id, then resolve the TARGET id (prod may have
        # generated its own uuid on a prior partial ingest).
        payload = {k: d[k] for k in d if k != "id"}
        tgt.execute(
            f"""INSERT INTO documents ({_DOC_COLS})
                VALUES ({", ".join("%(" + c.strip() + ")s" for c in _DOC_COLS.split(","))})
                ON CONFLICT (doc_id) DO UPDATE SET
                  content_class=EXCLUDED.content_class, document_status=EXCLUDED.document_status,
                  checksum_sha256=EXCLUDED.checksum_sha256, subject_tags=EXCLUDED.subject_tags;""",
            payload,
        )
        tgt_id = tgt.execute(
            "SELECT id FROM documents WHERE doc_id = %s;", (d["doc_id"],)
        ).fetchone()["id"]
        tgt.execute("DELETE FROM chunks WHERE document_id = %s;", (tgt_id,))
        for c in chunks:
            tgt.execute(
                """INSERT INTO chunks
                     (document_id, chunk_index, content, char_count, page_start,
                      page_end, content_hash, status, embedding)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::vector);""",
                (tgt_id, c["chunk_index"], c["content"], c["char_count"],
                 c["page_start"], c["page_end"], c["content_hash"], c["status"], c["emb"]),
            )
    return len(docs), n_chunks


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not args.apply)
    _db_target.ensure_reachable(target)
    print(f"Source (read): {args.source_url.split('@')[-1]}")

    with psycopg.connect(args.source_url, row_factory=dict_row) as src_conn, \
         psycopg.connect(target.url, row_factory=dict_row) as tgt_conn:
        src = src_conn.cursor()
        tgt = tgt_conn.cursor()
        n_ch = _sync_media_channels(src, tgt, args.apply)
        n_ref = _sync_media_refs(src, tgt, args.apply)
        n_doc, n_chunks = _sync_documents_and_chunks(src, tgt, args.apply)
        if args.apply:
            tgt_conn.commit()

    verb = "copied" if args.apply else "would copy"
    print(f"\n{verb}: {n_ch} channel(s), {n_ref} media_ref(s), {n_doc} how-to doc(s), "
          f"{n_chunks} chunk(s) with embeddings.")
    if not args.apply:
        print("Dry run — nothing written. Re-run with --apply.")
    else:
        print("Done. No YouTube fetch, no re-embed. A diy query on prod now hits these "
              "semantically. (match_chunks compliance path unchanged — how_to is segregated.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
