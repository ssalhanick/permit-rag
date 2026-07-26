"""
scripts/crawl_media_channels.py — enumerate vetted channels → media_refs (H2-6).

Vet a CHANNEL once; the crawler enumerates its recent uploads via the free RSS
feed (no API key/quota, ~latest 15) and upserts one media_refs row per video.
Semantic links (H2-6.1) surface these with no hand-assigned task_key, so a crawled
video is immediately useful. After crawling, run ingest_media_transcripts.py to
fetch transcripts + embed (the how-to answer corpus).

Target-safe via scripts/_db_target. Dry-run by default; --apply writes.

    # add a vetted channel
    py scripts/crawl_media_channels.py --local --add-channel UCxxxx --name "This Old House"
    # crawl all active channels → media_refs (dry-run, then apply)
    py scripts/crawl_media_channels.py --local
    py scripts/crawl_media_channels.py --local --apply
    # then ingest transcripts for the new rows
    py scripts/ingest_media_transcripts.py --local --apply
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Crawl vetted YouTube channels into media_refs.")
    p.add_argument("--local", action="store_true", help="Force .env.local target.")
    p.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    p.add_argument("--apply", action="store_true", help="Write rows (default: dry-run).")
    p.add_argument("--add-channel", help="Add a vetted channel by YouTube channel id (UC…), then exit.")
    p.add_argument("--name", help="Channel display name (with --add-channel).")
    p.add_argument("--jurisdiction", help="Channel jurisdiction (default: national / NULL).")
    p.add_argument("--vetted-by", help="Who approved this channel.")
    return p.parse_args(argv)


def _task_key_for(title: str) -> str:
    """Derive a media task_key from a video title: the curated keyword map first,
    else a slug of the title (semantic links don't need an exact key — this is a
    descriptive, non-null label)."""
    from rag.agents.media import _derive_task_key

    derived = _derive_task_key(title, None)
    if derived:
        return derived
    slug = re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")
    return slug[:60] or "how_to_video"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not (args.apply or args.add_channel))
    _db_target.ensure_reachable(target)

    from db.client import (
        insert_media_channel,
        insert_media_ref,
        list_media_channels,
        touch_media_channel_crawled,
    )

    if args.add_channel:
        if not args.name:
            print("--add-channel requires --name")
            return 1
        row = insert_media_channel(
            channel_id=args.add_channel, name=args.name,
            jurisdiction=args.jurisdiction, vetted_by=args.vetted_by,
        )
        print(f"Channel upserted: {row['name']} ({row['channel_id']})")
        return 0

    from ingestion.youtube_channel import channel_videos

    channels = list_media_channels(active_only=True)
    print(f"\n{len(channels)} active channel(s) (apply={args.apply}):\n")
    total_new = 0
    for ch in channels:
        videos = channel_videos(ch["channel_id"])
        print(f"  {ch['name']} ({ch['channel_id']}) — {len(videos)} recent upload(s)")
        for v in videos:
            task_key = _task_key_for(v["title"])
            if not args.apply:
                print(f"    [dry-run] {task_key:28} {v['url']}  {v['title'][:50]}")
                continue
            row = insert_media_ref(
                task_key=task_key, title=v["title"], url=v["url"],
                jurisdiction=ch.get("jurisdiction"), channel_id=ch["channel_id"],
            )
            status = "new" if row else "exists"
            if row:
                total_new += 1
            print(f"    [{status}] {task_key:28} {v['url']}")
        if args.apply and videos:
            touch_media_channel_crawled(ch["channel_id"])

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply.")
    else:
        print(f"\nDone. {total_new} new media_refs row(s). "
              "Next: py scripts/ingest_media_transcripts.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
