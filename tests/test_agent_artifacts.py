"""
tests/test_agent_artifacts.py — the artifact store.

The store exists for one reason: the Manager must never hold raw text. These
tests pin that property directly (a summary containing chunk content is a bug,
not a cosmetic issue) plus the mechanics — TTL expiry, missing refs, and the
deterministic token estimate the Budget Governor reads.
"""

from __future__ import annotations

import pytest

from rag.agents.artifacts import (
    DEFAULT_TTL_SECONDS,
    ArtifactRef,
    ArtifactStore,
    ExpiredArtifactError,
    MissingArtifactError,
    estimate_tokens,
)


def test_put_returns_a_ref_not_the_payload() -> None:
    """The whole point: callers get a handle, never the object."""
    store = ArtifactStore()
    ref = store.put("chunks", [{"content": "SECRET-TEXT"}], summary="1 chunk")

    assert isinstance(ref, ArtifactRef)
    assert ref.kind == "chunks"
    assert "SECRET-TEXT" not in ref.summary
    assert "SECRET-TEXT" not in ref.describe()


def test_get_resolves_the_same_object() -> None:
    """Resolution is identity, not a copy — the generator needs the real chunks."""
    store = ArtifactStore()
    payload = [{"doc_id": "dallas-building"}]
    assert store.get(store.put("chunks", payload, summary="1 chunk")) is payload


def test_get_accepts_a_bare_id() -> None:
    """Refs travel as ids through trace rows, so ids must resolve too."""
    store = ArtifactStore()
    ref = store.put("answer", "text", summary="an answer")
    assert store.get(ref.id) == "text"


def test_missing_ref_raises() -> None:
    """An unknown id is a bug in the plan, not something to paper over."""
    with pytest.raises(MissingArtifactError):
        ArtifactStore().get("chunks-doesnotexist")


def test_expired_ref_raises_rather_than_returning_stale_context() -> None:
    """A TTL breach must fail loudly — stale context in a compliance answer is worse."""
    store = ArtifactStore(default_ttl=0)
    ref = store.put("chunks", ["x"], summary="1 chunk")
    assert ref.is_expired(now=ref.created_at + 1)
    with pytest.raises(ExpiredArtifactError):
        store.get(ref)


def test_get_or_none_swallows_both_failures() -> None:
    """Optional artifacts (project context) resolve to None, never an exception."""
    store = ArtifactStore()
    assert store.get_or_none(None) is None
    assert store.get_or_none("chunks-nope") is None


def test_default_ttl_outlives_a_request() -> None:
    """15 minutes is longer than any single /query/answer round trip."""
    assert DEFAULT_TTL_SECONDS >= 900


def test_estimate_tokens_is_deterministic_and_shape_agnostic() -> None:
    """Same input, same number — an unstable estimate makes a cap unreproducible."""
    payload = [{"content": "x" * 400}, {"content": "y" * 400}]
    assert estimate_tokens(payload) == estimate_tokens(payload)
    assert estimate_tokens("z" * 400) == 100
    assert estimate_tokens(None) == 0


def test_store_reports_ids_and_total_tokens() -> None:
    """agent_steps.artifact_refs wants ids; the governor wants the total."""
    store = ArtifactStore()
    store.put("chunks", "a" * 400, summary="chunks")
    store.put("answer", "b" * 800, summary="answer")

    assert len(store) == 2
    assert len(store.ref_ids()) == 2
    assert all(isinstance(i, str) for i in store.ref_ids())
    assert store.total_tokens() == 300
