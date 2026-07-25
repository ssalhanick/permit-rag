"""
tests/test_metadata_agent.py — Corpus Metadata Validator (agent #13)
====================================================================
Fully mocked; runs on the repo machine (empty DB, no corpus). Covers the
deterministic checks, chunk sampling, proposal assembly (citations included),
and validate_document's governance routing — that it proposes rather than
writes, never drafts a live doc on the backfill path, and drafts on the
ingest path.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ingestion import metadata_agent as ma

# ── fixtures ─────────────────────────────────────────────────


def _doc(**over) -> dict:
    row = {
        "id": uuid4(),
        "doc_id": "dallas-building-code",
        "municipality": "dallas",
        "authority_level": "municipal",
        "doc_type": "building_code",
        "subject_tags": ["building"],
        "effective_date": date(2021, 1, 1),
        "review_due": date(2027, 1, 1),
        "checksum_sha256": "abc",
        "document_status": "active",
    }
    row.update(over)
    return row


def _chunks(n: int) -> list[dict]:
    return [{"id": uuid4(), "chunk_index": i, "content": f"section {i} text"} for i in range(n)]


def _assessment(**over) -> ma.MetadataAssessment:
    base = dict(
        effective_date=ma.FieldProposal(value="2019-06-15", confidence=0.9,
                                        chunk_index=0, excerpt="adopted June 15, 2019"),
        doc_type=ma.FieldProposal(value="zoning_ordinance", confidence=0.8,
                                  chunk_index=1, excerpt="zoning"),
        authority_level=ma.FieldProposal(value="municipal", confidence=0.9,
                                         chunk_index=1, excerpt="city of dallas"),
        subject_tags=ma.TagProposal(tags=["zoning", "setbacks", "not_a_real_tag"],
                                    confidence=0.7, chunk_index=2, rationale="topics"),
        contradicts_current=False,
        contradiction_note="",
    )
    base.update(over)
    return ma.MetadataAssessment(**base)


# ── deterministic checks ─────────────────────────────────────


def test_enum_conformance_passes_valid_doc() -> None:
    assert ma.check_enum_conformance(_doc()) == []


def test_enum_conformance_flags_bad_doc_type_and_authority() -> None:
    failures = ma.check_enum_conformance(_doc(doc_type="nonsense", authority_level="galactic"))
    assert any("doc_type" in f for f in failures)
    assert any("authority_level" in f for f in failures)


def test_completeness_flags_null_effective_date() -> None:
    missing = ma.check_completeness(_doc(effective_date=None))
    assert "effective_date" in missing


def test_completeness_clean_when_all_present() -> None:
    assert ma.check_completeness(_doc()) == []


def test_supersession_detects_version_family() -> None:
    ids = ["city-of-dallas-ordiance-v1", "city-of-dallas-ordiance-v2",
           "city-of-dallas-ordiance-v3", "plano-fire-code"]
    fam = ma.detect_supersession_candidates("city-of-dallas-ordiance-v1", ids)
    assert fam == ["city-of-dallas-ordiance-v2", "city-of-dallas-ordiance-v3"]


def test_supersession_detects_datestamp_family() -> None:
    ids = ["dallas-amlegal-code", "dallas-amlegal-code-20260101"]
    assert ma.detect_supersession_candidates("dallas-amlegal-code", ids) == [
        "dallas-amlegal-code-20260101"
    ]


def test_supersession_empty_for_unique_doc() -> None:
    assert ma.detect_supersession_candidates("solo-doc", ["solo-doc", "other"]) == []


# ── sampling ─────────────────────────────────────────────────


def test_sample_chunks_returns_all_when_small() -> None:
    chunks = _chunks(4)
    assert ma.sample_chunks(chunks, k=12) == sorted(chunks, key=lambda c: c["chunk_index"])


def test_sample_chunks_spreads_across_document() -> None:
    sampled = ma.sample_chunks(_chunks(100), k=10)
    assert len(sampled) == 10
    indices = [c["chunk_index"] for c in sampled]
    assert indices[0] == 0 and indices[-1] > 80  # spans the document, not the cover page


def test_sample_chunks_empty() -> None:
    assert ma.sample_chunks([], k=5) == []


# ── proposal assembly ────────────────────────────────────────


def test_build_proposals_effective_date_carries_citation() -> None:
    doc = _doc(effective_date=None)
    sampled = _chunks(3)
    proposals, _ = ma.build_proposals(doc, _assessment(), sampled)
    date_p = next(p for p in proposals if p.field == "effective_date")
    assert date_p.proposed == date(2019, 6, 15)
    assert date_p.citation.chunk_index == 0
    assert date_p.citation.chunk_id == str(sampled[0]["id"])  # mapped back to a real chunk
    assert date_p.citation.excerpt


def test_build_proposals_replaces_catch_all_doc_type() -> None:
    doc = _doc(doc_type="other")
    proposals, _ = ma.build_proposals(doc, _assessment(), _chunks(3))
    assert any(p.field == "doc_type" and p.proposed == "zoning_ordinance" for p in proposals)


def test_build_proposals_no_doc_type_when_already_specific() -> None:
    # doc_type is already 'building_code' (not a catch-all); do not churn it.
    doc = _doc(doc_type="building_code")
    proposals, _ = ma.build_proposals(doc, _assessment(), _chunks(3))
    assert not any(p.field == "doc_type" for p in proposals)


def test_build_proposals_tags_filtered_to_controlled_vocab() -> None:
    doc = _doc(subject_tags=[])
    proposals, _ = ma.build_proposals(doc, _assessment(), _chunks(3))
    tag_p = next(p for p in proposals if p.field == "subject_tags")
    assert "not_a_real_tag" not in tag_p.proposed
    assert set(tag_p.proposed) == {"zoning", "setbacks"}


def test_build_proposals_records_contradiction() -> None:
    a = _assessment(contradicts_current=True, contradiction_note="text says frisco, meta says dallas")
    _, contradictions = ma.build_proposals(_doc(), a, _chunks(3))
    assert contradictions == ["text says frisco, meta says dallas"]


def test_every_proposal_has_a_citation() -> None:
    doc = _doc(effective_date=None, doc_type="other", subject_tags=[])
    proposals, _ = ma.build_proposals(doc, _assessment(), _chunks(3))
    assert proposals
    assert all(p.citation is not None for p in proposals)


# ── result decision ──────────────────────────────────────────


def test_decide_result_fail_on_enum() -> None:
    r = ma.ValidationReport(doc_id="x", enum_failures=["bad doc_type"])
    assert ma._decide_result(r) == "fail"


def test_decide_result_needs_review_on_gap() -> None:
    r = ma.ValidationReport(doc_id="x", completeness_failures=["effective_date"])
    assert ma._decide_result(r) == "needs_review"


def test_decide_result_pass_when_clean() -> None:
    assert ma._decide_result(ma.ValidationReport(doc_id="x")) == "pass"


# ── validate_document: governance routing ────────────────────


@pytest.fixture
def _patched(monkeypatch):
    """Patch db reads + run_agent + governance so validate_document is offline."""
    doc = _doc(effective_date=None)
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: doc)
    monkeypatch.setattr(db_client, "get_chunks_for_document", lambda _uuid: _chunks(5))
    monkeypatch.setattr(
        ma, "run_agent",
        lambda *a, **k: SimpleNamespace(parsed_output=_assessment()),
    )
    calls: dict = {}

    def _flag(doc_id, **kwargs):
        calls["flag"] = {"doc_id": doc_id, **kwargs}
        return {"id": uuid4()}

    monkeypatch.setattr(ma.governance, "flag_document_for_review", _flag)
    return doc, calls


def test_validate_document_proposes_and_files_item(_patched) -> None:
    _doc_row, calls = _patched
    report = ma.validate_document("dallas-building-code", file_action_items=True)
    assert report.result == "needs_review"
    assert any(p.field == "effective_date" for p in report.proposals)
    assert calls["flag"]["set_draft"] is False  # backfill path never drafts a live doc


def test_validate_document_dry_run_writes_nothing(_patched) -> None:
    _doc_row, calls = _patched
    report = ma.validate_document("dallas-building-code", file_action_items=False)
    assert "flag" not in calls  # governance never touched on a dry run
    assert report.proposals  # but the analysis still happened


def test_validate_document_ingest_path_drafts(_patched) -> None:
    _doc_row, calls = _patched
    ma.validate_document("dallas-building-code", file_action_items=True, draft_on_fail=True)
    assert calls["flag"]["set_draft"] is True  # a new incomplete doc is drafted


def test_validate_document_missing_doc_raises(monkeypatch) -> None:
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: None)
    with pytest.raises(ValueError):
        ma.validate_document("ghost")


def test_validate_document_no_llm_skips_model(monkeypatch) -> None:
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: _doc(effective_date=None))

    def _boom(*a, **k):
        raise AssertionError("run_agent must not be called with use_llm=False")

    monkeypatch.setattr(ma, "run_agent", _boom)
    report = ma.validate_document("dallas-building-code", use_llm=False, file_action_items=False)
    assert report.llm_used is False
    assert "effective_date" in report.completeness_failures


def test_validate_document_degrades_on_llm_failure(monkeypatch) -> None:
    """A failed LLM parse must degrade to the deterministic result, not drop the doc."""
    from db import client as db_client

    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: _doc(effective_date=None))
    monkeypatch.setattr(db_client, "get_chunks_for_document", lambda _uuid: _chunks(5))

    def _raise(*a, **k):
        raise ValueError("Invalid JSON: EOF while parsing a string")

    monkeypatch.setattr(ma, "run_agent", _raise)
    report = ma.validate_document("dallas-building-code", file_action_items=False)
    assert report.result == "needs_review"   # deterministic finding stands
    assert report.result != "error"          # not dropped
    assert report.llm_used is False
    assert report.llm_note and "ValueError" in report.llm_note
    assert report.proposals == []            # no LLM proposals, but the doc survives


def test_validate_corpus_llm_failure_is_not_an_error_row(monkeypatch) -> None:
    """validate_corpus keeps a degraded doc as needs_review, reserving 'error' for DB blows."""
    from db import client as db_client

    monkeypatch.setattr(db_client, "list_documents",
                        lambda: [{"doc_id": "dallas-building-code"}])
    monkeypatch.setattr(db_client, "get_document_by_doc_id", lambda _id: _doc(effective_date=None))
    monkeypatch.setattr(db_client, "get_chunks_for_document", lambda _uuid: _chunks(5))
    monkeypatch.setattr(ma, "run_agent",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("EOF")))
    reports = ma.validate_corpus(file_action_items=False)
    assert [r.result for r in reports] == ["needs_review"]
    assert reports[0].llm_note
