"""
tests/test_citation_verifier.py — Citation Verifier (agent #9)
=============================================================
Deterministic span-match first; the ambiguous leftovers go to a mocked
entailment call. No network — ``run_agent`` is monkeypatched where used.
"""

from __future__ import annotations

from types import SimpleNamespace

from rag.agents import citation_verifier as cv
from rag.agents.citation_verifier import verify_answer


def _chunk(doc_id: str, idx: int, content: str) -> dict:
    return {"doc_id": doc_id, "chunk_index": idx, "content": content}


def test_span_match_supports_a_grounded_claim() -> None:
    """A claim whose salient terms appear in the cited chunk passes, no LLM."""
    chunks = [_chunk("dallas-fence", 0, "A residential fence setback must be five feet from the property line.")]
    answer = "The residential fence setback must be five feet from the property line [dallas-fence, chunk 0]."
    res = verify_answer(answer, chunks, use_llm=False)
    assert res.citation_precision == 1.0
    assert res.claims[0].method == "span"
    assert res.claims[0].verdict == "supported"


def test_missing_chunk_is_unsupported_without_llm() -> None:
    """A citation pointing at a chunk retrieval never returned is unsupported."""
    chunks = [_chunk("dallas-fence", 0, "Fence rules.")]
    answer = "Permit fees are $250 [plano-fees, chunk 9]."
    res = verify_answer(answer, chunks, use_llm=False)
    assert res.unsupported
    assert res.claims[0].method == "missing_chunk"
    assert res.citation_precision == 0.0


def test_uncited_factual_sentence_is_flagged() -> None:
    """A substantive sentence with no citation is flagged as uncited."""
    chunks = [_chunk("d", 0, "x")]
    answer = "Electrical panel upgrades require a permit and inspection before energizing."
    res = verify_answer(answer, chunks, use_llm=False)
    assert len(res.uncited) == 1
    # No cited claims → precision is vacuously 1.0, but recall gap shows in uncited.
    assert res.citation_precision == 1.0


def test_ambiguous_claim_goes_to_entailment(monkeypatch) -> None:
    """A middling-overlap claim is resolved by the batched entailment call."""
    chunks = [_chunk("code", 0, "The maximum structure height permitted in this district is thirty-five feet overall.")]
    # Paraphrase: partial overlap, so it lands in the leftovers, not a span pass.
    answer = "The building height limit applies overall here [code, chunk 0]."

    def _fake_run_agent(*_a, **_k):
        batch = cv._EntailmentBatch(verdicts=[cv._Entailment(index=0, supported=True)])
        return SimpleNamespace(parsed_output=batch)

    monkeypatch.setattr(cv, "run_agent", _fake_run_agent)
    res = verify_answer(answer, chunks, use_llm=True)
    assert res.claims[0].method == "entailment"
    assert res.claims[0].verdict == "supported"


def test_entailment_skipped_leaves_leftover_unsupported() -> None:
    """With use_llm=False an ambiguous claim stays unsupported (conservative)."""
    chunks = [_chunk("code", 0, "The maximum structure height permitted in this district is thirty-five feet overall.")]
    answer = "The building height limit applies overall here [code, chunk 0]."
    res = verify_answer(answer, chunks, use_llm=False)
    assert res.claims[0].verdict == "unsupported"


def test_entailment_failure_is_non_fatal(monkeypatch) -> None:
    """If the entailment call raises, the answer still verifies (leftovers unsupported)."""
    chunks = [_chunk("code", 0, "The maximum structure height permitted in this district is thirty-five feet overall.")]
    answer = "The building height limit applies overall here [code, chunk 0]."

    def _boom(*_a, **_k):
        raise RuntimeError("model down")

    monkeypatch.setattr(cv, "run_agent", _boom)
    res = verify_answer(answer, chunks, use_llm=True)
    assert res.claims[0].verdict == "unsupported"
