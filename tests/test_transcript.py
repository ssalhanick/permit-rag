"""
tests/test_transcript.py — YouTube transcript fetch (Media Curator Slice C).

Covers URL→id extraction across the URL shapes, and fetch_transcript's join +
graceful degradation (missing captions / non-youtube URLs return None, never
raise — ingest is best-effort).
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from ingestion import transcript


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=TqTNJUT_lKg", "TqTNJUT_lKg"),
        ("https://youtube.com/watch?v=TqTNJUT_lKg&t=30s", "TqTNJUT_lKg"),
        ("https://youtu.be/TqTNJUT_lKg", "TqTNJUT_lKg"),
        ("https://m.youtube.com/watch?v=TqTNJUT_lKg", "TqTNJUT_lKg"),
        ("https://www.youtube.com/shorts/TqTNJUT_lKg", "TqTNJUT_lKg"),
        ("https://www.youtube.com/embed/TqTNJUT_lKg", "TqTNJUT_lKg"),
        ("https://vimeo.com/123456789", None),
        ("https://www.youtube.com/watch?v=tooshort", None),
        ("not a url", None),
    ],
)
def test_video_id_from_url(url: str, expected: str | None) -> None:
    assert transcript.video_id_from_url(url) == expected


def _install_fake_api(monkeypatch: pytest.MonkeyPatch, *, segments: Any = None, raises: Exception | None = None) -> None:
    """Inject a fake youtube_transcript_api module (1.x instance .fetch() API)."""
    mod = types.ModuleType("youtube_transcript_api")

    class _Fetched:
        def __init__(self, data: Any) -> None:
            self._data = data

        def to_raw_data(self) -> Any:
            return self._data

    class _Api:
        def fetch(self, video_id: str, languages: list[str] | None = None) -> Any:
            if raises is not None:
                raise raises
            return _Fetched(segments)

    mod.YouTubeTranscriptApi = _Api  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", mod)


def test_fetch_transcript_joins_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_api(monkeypatch, segments=[
        {"text": "First line"}, {"text": "second   line"}, {"text": ""},
    ])
    text = transcript.fetch_transcript("https://youtu.be/TqTNJUT_lKg")
    assert text == "First line second line"


def test_fetch_transcript_none_on_no_captions(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_api(monkeypatch, raises=RuntimeError("TranscriptsDisabled"))
    assert transcript.fetch_transcript("https://youtu.be/TqTNJUT_lKg") is None


def test_fetch_transcript_none_on_non_youtube_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # Not a youtube URL → returns before any API import.
    assert transcript.fetch_transcript("https://vimeo.com/123") is None


def test_fetch_transcript_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_api(monkeypatch, segments=[{"text": "   "}, {"text": ""}])
    assert transcript.fetch_transcript("https://youtu.be/TqTNJUT_lKg") is None
