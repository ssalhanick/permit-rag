"""
tests/test_agent_eval.py — Evaluator (agent #23)
================================================
Per-agent metric-contract scoring over the trace store. The DB readers and the
RAGAs faithfulness source are monkeypatched — no DB, no files, no model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

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


# ── gates=False / LangSmith advisory metrics ──────────────────


def test_advisory_check_never_breaches_or_demotes(monkeypatch) -> None:
    """A failing gates=False check is an advisory, never a breach or demotion."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "answer_generator", "calls": 50, "deterministic_rate": 0.0,
                    "error_rate": 0.0, "avg_latency_ms": 900}],
        faithfulness=0.90,  # clears the gating faithfulness check
    )
    monkeypatch.setattr(
        agent_eval, "_latest_langsmith_metrics",
        lambda: {"answer_generator": {"langsmith_hallucination_judge": 0.5}},  # below 0.85
    )
    filed = {}
    monkeypatch.setattr(
        agent_eval.db_client, "upsert_action_item", lambda **k: filed.update(k) or {"id": "x"}
    )
    reports = agent_eval.evaluate(since=datetime.now(UTC), apply=True)
    r = reports[0]
    assert r.passed is True
    assert r.breaches == []
    assert any("hallucination" in a for a in r.advisories)
    assert filed == {}
    assert r.demoted_to is None


def test_promoted_check_gates_like_any_other_contract(monkeypatch) -> None:
    """Flipping a specific agent's check to gates=True behaves exactly like the
    pre-existing (always-gating) contracts -- the per-agent middle ground."""
    _patch_sources(
        monkeypatch,
        scorecard=[{"agent_name": "manager", "calls": 10, "deterministic_rate": 1.0,
                    "error_rate": 0.0, "avg_latency_ms": 5}],
    )
    monkeypatch.setattr(
        agent_eval, "_latest_langsmith_metrics",
        lambda: {"manager": {"langsmith_project_isolation": 0.5}},  # below 1.0
    )
    promoted = tuple(
        Check(c.metric, c.op, c.threshold, c.label, gates=True)
        for c in agent_eval.CONTRACTS["manager"]
    )
    monkeypatch.setitem(agent_eval.CONTRACTS, "manager", promoted)
    monkeypatch.setattr(agent_eval.db_client, "upsert_action_item", lambda **k: {"id": "x"})
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
    assert any("project-isolation" in b for b in r.breaches)
    assert r.demoted_to == "L1"


def test_langsmith_metrics_skips_stale_experiment(monkeypatch) -> None:
    """An experiment tagged with a different prompt/library version than what's
    deployed is not trusted -- reports nothing rather than a wrong number."""
    class _FakeProject:
        name = "old-experiment"
        start_time = datetime.now(UTC)
        metadata: ClassVar = {"prompt_version": "v1", "library_version": "old-lib"}
        feedback_stats: ClassVar = {"hallucination_judge": {"avg": 0.5}}

    monkeypatch.setattr(agent_eval, "_latest_experiment", lambda dataset: _FakeProject())
    import rag.generator
    import rag.prompts
    monkeypatch.setattr(rag.generator, "PROMPT_VERSION", "v99-different")
    monkeypatch.setattr(rag.prompts, "library_version", lambda: "new-lib")

    assert agent_eval._latest_langsmith_metrics() == {}


def test_langsmith_metrics_reports_version_matched_experiment(monkeypatch) -> None:
    """A version-matched experiment's scores flow through as advisory metrics,
    attributed to the agents configured in _LANGSMITH_SOURCES.

    _aggregate_feedback is mocked directly (not Project.feedback_stats) --
    confirmed empirically 2026-08-06 against a real experiment that
    Project.feedback_stats is never populated for a run() via
    langsmith.evaluation.evaluate(); the real fetch aggregates individual
    list_feedback() rows instead. See _aggregate_feedback's docstring.
    """
    class _FakeProject:
        name = "fresh-experiment"
        start_time = datetime.now(UTC)
        metadata: ClassVar = {"prompt_version": "v3", "library_version": "lib-v3"}

    monkeypatch.setattr(agent_eval, "_latest_experiment", lambda dataset: _FakeProject())
    monkeypatch.setattr(
        agent_eval, "_aggregate_feedback",
        lambda experiment: {
            "hallucination_judge": 0.9,
            "citation_precision": 0.85,
            "citation_recall": 0.75,
            "project_isolation": 1.0,
        },
    )
    import rag.generator
    import rag.prompts
    monkeypatch.setattr(rag.generator, "PROMPT_VERSION", "v3")
    monkeypatch.setattr(rag.prompts, "library_version", lambda: "lib-v3")

    result = agent_eval._latest_langsmith_metrics()
    assert result["answer_generator"]["langsmith_hallucination_judge"] == 0.9
    assert result["answer_generator"]["langsmith_citation_precision"] == 0.85
    assert result["answer_generator"]["langsmith_citation_recall"] == 0.75
    assert result["manager"]["langsmith_project_isolation"] == 1.0


def test_aggregate_feedback_computes_mean_per_key(monkeypatch) -> None:
    """_aggregate_feedback means multiple runs' scores per key, skipping
    None-score feedback rows (e.g. citation checks skipped for an example)."""
    class _FakeExperiment:
        id = "exp-1"

    class _FakeRun:
        def __init__(self, run_id):
            self.id = run_id

    class _FakeFeedback:
        def __init__(self, key, score):
            self.key = key
            self.score = score

    class _FakeClient:
        def list_runs(self, *, project_id, execution_order):
            return [_FakeRun("run-1"), _FakeRun("run-2")]

        def list_feedback(self, *, run_ids):
            per_run = {
                "run-1": [_FakeFeedback("project_isolation", 1.0),
                          _FakeFeedback("citation_precision", None)],
                "run-2": [_FakeFeedback("project_isolation", 0.0)],
            }
            return per_run[run_ids[0]]

    import langsmith
    monkeypatch.setattr(langsmith, "Client", lambda: _FakeClient())

    result = agent_eval._aggregate_feedback(_FakeExperiment())
    assert result == {"project_isolation": 0.5}  # mean of 1.0 and 0.0
    assert "citation_precision" not in result  # None-score rows excluded


def test_langsmith_metrics_degrades_on_lookup_failure(monkeypatch) -> None:
    """LangSmith being unreachable (or any unexpected error in the lookup) must
    never break the Evaluator -- degrades to no advisory metrics."""
    def _boom(dataset):
        raise RuntimeError("network is down")

    monkeypatch.setattr(agent_eval, "_latest_experiment", _boom)
    assert agent_eval._latest_langsmith_metrics() == {}


def test_langsmith_metrics_absent_when_no_experiment_exists(monkeypatch) -> None:
    """No experiment on record for a dataset -- no advisory metrics, no error."""
    monkeypatch.setattr(agent_eval, "_latest_experiment", lambda dataset: None)
    assert agent_eval._latest_langsmith_metrics() == {}
