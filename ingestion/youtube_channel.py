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
import re
from xml.etree import ElementTree as ET

log = logging.getLogger(__name__)

_FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
# A YouTube channel id is "UC" + 22 url-safe chars.
_CHANNEL_ID_RE = re.compile(r"UC[0-9A-Za-z_-]{22}")
_UA = "Mozilla/5.0 (compatible; permit-rag-media-curator/1.0)"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}
_WATCH_URL = "https://www.youtube.com/watch?v={video_id}"


def _to_channel_url(value: str) -> str:
    """Build a fetchable channel URL from a handle / custom-URL / full URL."""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if "youtube.com" in value:
        return "https://" + value.lstrip("/")
    if value.startswith("@"):
        return f"https://www.youtube.com/{value}"
    return f"https://www.youtube.com/@{value}"  # bare name → try as a handle


def resolve_channel_id(value: str, *, timeout: int = 10) -> str | None:
    """Resolve a channel id (``UC…``) from an id, @handle, or channel URL.

    - A bare ``UC…`` id, or a ``/channel/UC…`` URL → extracted directly (no fetch).
    - A ``@handle``, ``/c/name``, ``/user/name``, or bare name → fetch the channel
      page and read the id from its canonical link (or the embedded metadata).

    Returns None when it can't be resolved (bad handle, network/consent block) —
    the caller reports and aborts rather than inserting a bogus channel.
    """
    v = (value or "").strip()
    if not v:
        return None
    if _CHANNEL_ID_RE.fullmatch(v):
        return v
    if "/channel/" in v:
        m = _CHANNEL_ID_RE.search(v)
        if m:
            return m.group(0)

    url = _to_channel_url(v)
    try:
        import requests

        resp = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        log.warning("resolve_channel_id: could not fetch %s (%s): %s", url, v, exc)
        return None

    # The canonical link is the reliable source; fall back to embedded metadata.
    patterns = (
        r'rel="canonical" href="https://www\.youtube\.com/channel/(UC[0-9A-Za-z_-]{22})"',
        r'"channelId":"(UC[0-9A-Za-z_-]{22})"',
        r'"externalId":"(UC[0-9A-Za-z_-]{22})"',
        r'itemprop="identifier" content="(UC[0-9A-Za-z_-]{22})"',
    )
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    log.warning("resolve_channel_id: no channel id found on %s", url)
    return None


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
