"""
ingestion/youtube_channel.py — enumerate a YouTube channel's recent uploads.
============================================================================
Channel-level Media Curator ingest (H2-6). Uses YouTube's **free** per-channel
RSS/Atom feed — no API key, no quota — which returns roughly the latest 15
uploads. That's enough to keep vetted channels fresh on a periodic crawl; a full
back-catalogue pull (Data API / yt-dlp) is deferred until volume requires it.

Import boundary: ingestion/ → db/, stdlib. ``requests`` is a third-party dep used
across ingestion (harvester); the XML parse is stdlib. Touches no DB.
"""

from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}
_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def channel_videos(channel_id: str, *, timeout: int = 10) -> list[dict]:
    """Return recent uploads for a channel, or [] on any failure.

    Each item: ``{video_id, title, url, published}``. Best-effort — a network
    error, a private/empty channel, or a malformed feed logs a warning and
    returns [], so a crawl over many channels never aborts on one bad channel.
    """
    if not channel_id:
        return []
    try:
        import requests

        resp = requests.get(_FEED_URL.format(channel_id=channel_id), timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as exc:  # network / HTTP / parse
        log.warning("channel_videos: could not fetch/parse feed for %s: %s", channel_id, exc)
        return []

    videos: list[dict] = []
    for entry in root.findall("atom:entry", _NS):
        vid_el = entry.find("yt:videoId", _NS)
        title_el = entry.find("atom:title", _NS)
        pub_el = entry.find("atom:published", _NS)
        if vid_el is None or not (vid_el.text or "").strip():
            continue
        video_id = vid_el.text.strip()
        videos.append({
            "video_id": video_id,
            "title": (title_el.text or "").strip() if title_el is not None else video_id,
            "url": _WATCH_URL.format(video_id=video_id),
            "published": (pub_el.text or "").strip() if pub_el is not None else None,
        })
    return videos
