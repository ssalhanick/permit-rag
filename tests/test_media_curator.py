"""
tests/test_media_curator.py — the Media Curator (agent #17, Phase 4 second pass).

The Curator surfaces sourced how-to videos on the diy path only, deriving a
task_key from the query and looking it up in the curated ``media_refs`` table. It
never fabricates a URL: everything it returns comes from the table (this B1
slice), so the "zero unsourced URLs" gate holds by construction.
"""

from __future__ import annotations

from typing import Any

import pytest

from rag.agents import media


class _FetchRecorder:
    """Captures db.client.fetch_media_refs calls and returns a canned result."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    def __call__(self, task_key: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"task_key": task_key, **kwargs})
        return self.rows


def _row(task_key: str, **over: Any) -> dict[str, Any]:
    base = {
        "task_key": task_key,
        "title": "How to install a GFCI outlet",
        "url": "https://www.youtube.com/watch?v=abc123",
        "provider": "youtube",
        "jurisdiction": None,
        "relevance_note": "Step-by-step GFCI install",
        "last_verified_at": None,
    }
    base.update(over)
    return base


@pytest.fixture()
def fetch(monkeypatch: pytest.MonkeyPatch) -> _FetchRecorder:
    import db.client as db_client

    rec = _FetchRecorder([_row("install_gfci_outlet")])
    monkeypatch.setattr(db_client, "fetch_media_refs", rec)
    return rec


def test_diy_query_returns_sourced_videos(fetch: _FetchRecorder) -> None:
    refs = media.curate(
        "how do I install a gfci outlet", persona="diy", jurisdiction="dallas"
    )
    assert len(refs) == 1
    assert refs[0].title == "How to install a GFCI outlet"
    assert refs[0].sourced is True  # every ref is vetted
    # jurisdiction threaded through to the lookup
    assert fetch.calls[0]["task_key"] == "install_gfci_outlet"
    assert fetch.calls[0]["jurisdiction"] == "dallas"


def test_non_diy_persona_gets_nothing(fetch: _FetchRecorder) -> None:
    for persona in ("contractor", "hiring_contractor", "research", None):
        assert media.curate("install a gfci outlet", persona=persona) == []
    assert fetch.calls == []  # no DB lookup at all for non-diy


def test_query_with_no_curated_task_gets_nothing(fetch: _FetchRecorder) -> None:
    assert media.curate("what is the setback requirement", persona="diy") == []
    assert fetch.calls == []  # task_key derivation misses → no lookup


def test_task_key_derivation_first_match_wins() -> None:
    assert media._derive_task_key("replace my kitchen faucet", None) == "replace_faucet"
    assert media._derive_task_key("build a backyard deck", None) == "build_deck"
    assert media._derive_task_key("install a ceiling fan", None) == "install_ceiling_fan"
    assert media._derive_task_key("pour a foundation", None) is None


def test_lookup_failure_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import db.client as db_client

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(db_client, "fetch_media_refs", _boom)
    # A media failure degrades to no videos, never breaks the answer path.
    assert media.curate("install a gfci outlet", persona="diy") == []
