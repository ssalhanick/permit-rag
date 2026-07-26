"""
ingestion/transcript.py — fetch a YouTube video transcript.
============================================================
The Media Curator (agent #17) surfaces vetted how-to videos. Slice C ingests
their *transcripts* so a DIY how-to query can be grounded on how-to content —
stored as a segregated, non-authoritative class that never grounds a compliance
answer (migration 031).

This module only fetches + normalizes transcript text; chunking and embedding
reuse ``ingestion.chunker.split_text`` and ``ingestion.embedder``. No API cost:
captions are pulled from YouTube's public transcript endpoint via
``youtube-transcript-api``.

Import boundary: ingestion/ → db/, stdlib (AGENTS.md). This module touches no DB;
the third-party ``youtube_transcript_api`` is a stdlib-external dependency used
only here and imported lazily so importing the package stays cheap.
"""

from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)


class TranscriptBlocked(Exception):
    """YouTube is rate-limiting / IP-blocking transcript requests.

    Distinct from "no captions": a block is not fixable by retrying the same
    video from the same IP, so the caller should back off / stop the run rather
    than hammer a blocked IP (see the Media Curator H2-6 ops note — run from a
    residential IP or a proxy at channel scale).
    """


_BLOCK_MARKERS = (
    "requestblocked", "ipblocked", "blocking requests from your ip",
    "too many requests", "ip has been blocked",
)
_NO_TRANSCRIPT_MARKERS = ("notranscript", "transcriptsdisabled", "nofound", "no transcript")


def _classify(exc: Exception) -> str:
    """'blocked' | 'no_transcript' | 'transient' for a fetch exception."""
    s = (type(exc).__name__ + " " + str(exc)).lower()
    if "block" in type(exc).__name__.lower() or any(m in s for m in _BLOCK_MARKERS):
        return "blocked"
    if any(m in s for m in _NO_TRANSCRIPT_MARKERS):
        return "no_transcript"
    return "transient"

# youtube.com/watch?v=ID · youtu.be/ID · youtube.com/shorts/ID · /embed/ID
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def video_id_from_url(url: str) -> str | None:
    """Extract the 11-char YouTube video id from a URL, or None.

    Handles the watch, youtu.be, shorts, and embed URL shapes. Returns None for
    anything that is not a recognizable YouTube video URL.
    """
    try:
        parsed = urlparse(url)
    except (ValueError, AttributeError):
        return None
    host = (parsed.hostname or "").lower().removeprefix("www.")

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]
    elif host in {"youtube.com", "m.youtube.com", "music.youtube.com"}:
        if parsed.path == "/watch":
            candidate = (parse_qs(parsed.query).get("v") or [""])[0]
        elif parsed.path.startswith(("/shorts/", "/embed/", "/v/")):
            candidate = parsed.path.split("/", 2)[2].split("/", 1)[0]
        else:
            candidate = ""
    else:
        return None

    return candidate if _ID_RE.match(candidate) else None


def fetch_transcript(
    url: str,
    *,
    languages: tuple[str, ...] = ("en",),
    retries: int = 1,
    backoff: float = 2.0,
) -> str | None:
    """Return the joined transcript text for a video URL, or None.

    None is a normal outcome — captions may be disabled, absent, or only in a
    language we did not ask for. A *block* (rate-limit / IP ban) raises
    :class:`TranscriptBlocked` instead, so the caller can back off or stop rather
    than retry a blocked IP. A transient error is retried up to ``retries`` times
    with linear ``backoff``.
    """
    vid = video_id_from_url(url)
    if vid is None:
        log.warning("transcript: not a recognizable YouTube URL: %s", url)
        return None

    segments = None
    for attempt in range(retries + 1):
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            # 1.x: instance .fetch() → FetchedTranscript; .to_raw_data() gives
            # [{'text','start','duration'}, ...]. (0.x get_transcript was removed.)
            segments = YouTubeTranscriptApi().fetch(vid, languages=list(languages)).to_raw_data()
            break
        except Exception as exc:
            kind = _classify(exc)
            if kind == "blocked":
                raise TranscriptBlocked(str(exc)) from exc
            if kind == "no_transcript" or attempt >= retries:
                log.warning("transcript: no transcript for %s (%s): %s", vid, url, exc)
                return None
            time.sleep(backoff * (attempt + 1))  # transient — back off and retry

    text = " ".join(seg["text"].strip() for seg in segments if seg.get("text"))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        log.warning("transcript: empty transcript for %s", vid)
        return None
    return text
