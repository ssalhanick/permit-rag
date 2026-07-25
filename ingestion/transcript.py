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
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)

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


def fetch_transcript(url: str, *, languages: tuple[str, ...] = ("en",)) -> str | None:
    """Return the joined transcript text for a video URL, or None.

    None is a normal outcome — captions may be disabled, absent, or only in a
    language we did not ask for. The caller skips those videos rather than
    ingesting an empty document. Never raises for the expected "no transcript"
    cases; unexpected errors are logged and swallowed (ingest is best-effort).
    """
    vid = video_id_from_url(url)
    if vid is None:
        log.warning("transcript: not a recognizable YouTube URL: %s", url)
        return None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        segments = YouTubeTranscriptApi.get_transcript(vid, languages=list(languages))
    except Exception as exc:  # NoTranscriptFound / TranscriptsDisabled / network
        log.warning("transcript: no transcript for %s (%s): %s", vid, url, exc)
        return None

    text = " ".join(seg["text"].strip() for seg in segments if seg.get("text"))
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        log.warning("transcript: empty transcript for %s", vid)
        return None
    return text
