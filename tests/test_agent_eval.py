"""
tests/test_agent_eval.py — Evaluator (agent #23)
================================================
Per-agent metric-contract scoring over the trace store. The DB readers and the
RAGAs faithfulness source are monkeypatched — no DB, no files, no model.
"""

from __future__ import annotations

from datetime import UTC, datetime

from evaluation import agent_eval
from evaluation.agent_eval import Check


def _patch_sources(monkeypatch, *, scorecard, corrections=None, faithfulness=None):
    monkeypatch.setattr(agent_eval.db_client, "agent_scorecard", lambda *, since: scorecard)
    monkeypatch.setattr(
        agent_eval.db_client, "correction_rate_by_agent", lambda *, since: corrections or []
    )
    monkeypatch.setattr(agent_eval, "_latest_faithfulness", lambda _d: faithfulness)


def test_check_absent_metric_is_not_a_breach() -> None:
    """A metric the window can't measure returns None — never counts as failed."""
    chk = Check("faithfulness", "gte", 0.85, "x")
    assert chk.passes(None) is None
    assert chk.passes(0.9) is True
    assert chk.passes(0.5) is False


def test_clean_agent_passes(monkeypatch) -> None:
    """An agent inside every threshold reports no breaches."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "retriever", "calls": 100, "deterministic_rate": 1.0,
                    "error_rate": 0.0, "avg_latency_ms": 20}],
    )
    reports = agent_eval.evaluate(since=datetime.now(UTC))
    assert len(reports) == 1
    assert reports[0].passed is True


def test_faithfulness_breach_on_answer_generator(monkeypatch) -> None:
    """Low RAGAs faithfulness breaches the answer generator's contract."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "answer_generator", "calls": 50, "deterministic_rate": 0.0,
                    "error_rate": 0.0, "avg_latency_ms": 900}],
        faithfulness=0.80,  # below 0.85
    )
    reports = agent_eval.evaluate(since=datetime.now(UTC))
    r = reports[0]
    assert r.passed is False
    assert any("faithfulness" in b for b in r.breaches)


def test_correction_rate_breach(monkeypatch) -> None:
    """Confirmed corrections above 20% of calls breach the global contract."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "prompt_router", "calls": 10, "deterministic_rate": 1.0,
                    "error_rate": 0.0, "avg_latency_ms": 1}],
        corrections=[{"agent_name": "prompt_router", "confirmed_corrections": 3, "total_corrections": 3}],
    )
    reports = agent_eval.evaluate(since=datetime.now(UTC))
    assert reports[0].passed is False
    assert any("correction rate" in b for b in reports[0].breaches)


def test_apply_files_item_and_demotes(monkeypatch) -> None:
    """On a breach with apply=True, an action item is filed and autonomy drops."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "metadata_validator", "calls": 20, "deterministic_rate": 0.5,
                    "error_rate": 0.30, "avg_latency_ms": 500}],  # error_rate breach
    )
    filed = {}
    monkeypatch.setattr(
        agent_eval.db_client, "upsert_action_item",
        lambda **k: filed.update(k) or {"id": "item"},
    )
    monkeypatch.setattr(
        agent_eval.db_client, "get_agent_autonomy",
        lambda a, s="default": {"current_level": "L2", "max_level": "L2"},
    )
    monkeypatch.setattr(
        agent_eval.db_client, "set_agent_autonomy",
        lambda a, s, *, current_level, updated_by=None: {"current_level": current_level},
    )
    reports = agent_eval.evaluate(since=datetime.now(UTC), apply=True)
    r = reports[0]
    assert r.passed is False
    assert filed["kind"] == "metric_contract_breach"
    assert filed["entity_id"] == "metadata_validator"
    assert r.demoted_to == "L1"


def test_apply_does_not_demote_below_l0(monkeypatch) -> None:
    """An agent already at L0 is not demoted further."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "x", "calls": 5, "deterministic_rate": 1.0,
                    "error_rate": 0.5, "avg_latency_ms": 1}],
    )
    monkeypatch.setattr(agent_eval.db_client, "upsert_action_item", lambda **k: {"id": "i"})
    monkeypatch.setattr(
        agent_eval.db_client, "get_agent_autonomy",
        lambda a, s="default": {"current_level": "L0", "max_level": "L3"},
    )
    reports = agent_eval.evaluate(since=datetime.now(UTC), apply=True)
    assert reports[0].demoted_to is None
