"""
tests/test_youtube_channel.py — channel RSS enumeration (Media Curator H2-6).

Parses YouTube's per-channel Atom feed into {video_id, title, url}; degrades to
[] on any network/parse error so a crawl never aborts on one bad channel.
"""

from __future__ import annotations

from typing import Any

import pytest

from ingestion import youtube_channel

_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns="http://www.w3.org/2005/Atom">
  <title>Channel</title>
  <entry>
    <yt:videoId>abc123DEF45</yt:videoId>
    <title>How to install a GFCI outlet</title>
    <published>2025-01-01T00:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>xyz789GHI01</yt:videoId>
    <title>Wiring a 3-way switch</title>
    <published>2025-02-01T00:00:00+00:00</published>
  </entry>
</feed>
"""


class _Resp:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_channel_videos_parses_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests
    monkeypatch.setattr(requests, "get", lambda *_a, **_k: _Resp(_FEED))

    videos = youtube_channel.channel_videos("UCtestchannel")
    assert [v["video_id"] for v in videos] == ["abc123DEF45", "xyz789GHI01"]
    assert videos[0]["title"] == "How to install a GFCI outlet"
    assert videos[0]["url"] == "https://www.youtube.com/watch?v=abc123DEF45"


def test_channel_videos_empty_channel_id() -> None:
    assert youtube_channel.channel_videos("") == []


def test_channel_videos_network_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("blocked")

    monkeypatch.setattr(requests, "get", _boom)
    assert youtube_channel.channel_videos("UCtestchannel") == []


# ── Channel-id resolution (--add-channel) ────────────────────

_UC = "UC1234567890abcdefghABCD"  # UC + 22 chars


def test_resolve_bare_channel_id_no_fetch() -> None:
    assert youtube_channel.resolve_channel_id(_UC) == _UC


def test_resolve_channel_url_no_fetch() -> None:
    assert youtube_channel.resolve_channel_id(
        f"https://www.youtube.com/channel/{_UC}"
    ) == _UC


def test_resolve_handle_via_canonical_link(monkeypatch: pytest.MonkeyPatch) -> None:
    html = (
        '<html><head><link rel="canonical" '
        f'href="https://www.youtube.com/channel/{_UC}"></head></html>'
    )

    class _R:
        text = html
        def raise_for_status(self) -> None: return None

    import requests
    captured = {}

    def _get(url: str, **_k: Any) -> Any:
        captured["url"] = url
        return _R()

    monkeypatch.setattr(requests, "get", _get)
    assert youtube_channel.resolve_channel_id("@ThisOldHouse") == _UC
    assert captured["url"] == "https://www.youtube.com/@ThisOldHouse"


def test_resolve_returns_none_on_fetch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("consent block")

    monkeypatch.setattr(requests, "get", _boom)
    assert youtube_channel.resolve_channel_id("@nope") is None
