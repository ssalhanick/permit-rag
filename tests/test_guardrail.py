"""
tests/test_guardrail.py — the Guardrail truncation trip (agent #4, Phase 4).

When a generation stops on ``max_tokens`` the answer is cut off mid-content — a
bad, near-invisible compliance failure. The Guardrail files a deduped action
item so a human (and the anomaly detector) can see it, and it must never crash
the answer path doing so.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from rag.agents import guardrail


class _UpsertRecorder:
    """Captures calls to db.client.upsert_action_item."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"id": "item-1", **kwargs}


@pytest.fixture()
def upsert(monkeypatch: pytest.MonkeyPatch) -> _UpsertRecorder:
    """Swap the db writer the guardrail imports lazily."""
    import db.client as db_client

    rec = _UpsertRecorder()
    monkeypatch.setattr(db_client, "upsert_action_item", rec)
    return rec


def _gen(stop_reason: str) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, model="claude-haiku-4-5", output_tokens=2048)


def test_truncation_files_a_guardrail_action_item(upsert: _UpsertRecorder) -> None:
    tripped = guardrail.check_truncation(_gen("max_tokens"), query="how do i wire a panel")
    assert tripped is True
    assert len(upsert.calls) == 1
    call = upsert.calls[0]
    assert call["source_agent"] == "guardrail"
    assert call["kind"] == "answer_truncated"
    assert call["blocking"] is False
    assert call["evidence"]["stop_reason"] == "max_tokens"


def test_normal_stop_reason_files_nothing(upsert: _UpsertRecorder) -> None:
    tripped = guardrail.check_truncation(_gen("end_turn"), query="q")
    assert tripped is False
    assert upsert.calls == []


def test_guardrail_never_raises_even_if_the_writer_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import db.client as db_client

    def _boom(**_kwargs: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(db_client, "upsert_action_item", _boom)
    # Still reports the trip; swallows the write failure.
    assert guardrail.check_truncation(_gen("max_tokens"), query="q") is True


def test_entity_id_defaults_to_query_when_not_given(upsert: _UpsertRecorder) -> None:
    guardrail.check_truncation(_gen("max_tokens"), query="a compound question")
    assert upsert.calls[0]["entity_id"] == "a compound question"
