"""
tests/test_generator_chunk_filter.py — reranker-rejected chunks must not be prompted.

rag/reranker.py marks sub-threshold chunks filtered_out=True but still returns
them so the frontend can grey them out. Before this fix, api/routes/query.py
passed the full set into generate_answer, so rejected chunks were billed as
input tokens and diluted context -- including superseded documents demoted to
retrieval_weight=0.1, which AGENTS.md says must never be an answer's sole source.
"""

from __future__ import annotations

from typing import Any

from rag.generator import (
    _extract_citations,
    _format_chunks_for_prompt,
    drop_filtered_chunks,
)


def _chunk(doc_id: str, *, filtered_out: bool, index: int = 0) -> dict[str, Any]:
    """Build a retrieved-chunk dict shaped like rag.retriever output."""
    return {
        "doc_id": doc_id,
        "chunk_index": index,
        "municipality": "dallas",
        "authority_level": "municipal",
        "similarity": 0.42,
        "reranked_score": 0.11 if filtered_out else 0.68,
        "content": f"CONTENT-{doc_id}",
        "filtered_out": filtered_out,
    }


def test_drop_filtered_chunks_removes_only_rejected() -> None:
    """Passing chunks survive; rejected ones do not."""
    chunks = [
        _chunk("dallas-code", filtered_out=False),
        _chunk("superseded-v1", filtered_out=True),
        _chunk("plano-zoning", filtered_out=False),
    ]
    kept = drop_filtered_chunks(chunks)
    assert [c["doc_id"] for c in kept] == ["dallas-code", "plano-zoning"]


def test_chunks_without_the_flag_are_kept() -> None:
    """Absent filtered_out means the reranker never ran -- keep the chunk."""
    chunks = [{"doc_id": "no-flag", "content": "x"}]
    assert drop_filtered_chunks(chunks) == chunks


def test_rejected_chunk_content_never_reaches_the_prompt() -> None:
    """The token-cost regression: rejected content must be absent from the prompt."""
    chunks = [
        _chunk("kept-doc", filtered_out=False),
        _chunk("rejected-doc", filtered_out=True),
    ]
    prompt = _format_chunks_for_prompt(drop_filtered_chunks(chunks))

    assert "CONTENT-kept-doc" in prompt
    assert "CONTENT-rejected-doc" not in prompt
    assert "rejected-doc" not in prompt


def test_prompt_shrinks_when_chunks_are_rejected() -> None:
    """Directly asserts the input-token saving this fix exists for."""
    passing = [_chunk(f"doc-{i}", filtered_out=False, index=i) for i in range(7)]
    rejected = [_chunk(f"bad-{i}", filtered_out=True, index=i) for i in range(3)]

    unfiltered = _format_chunks_for_prompt(passing + rejected)
    filtered = _format_chunks_for_prompt(drop_filtered_chunks(passing + rejected))

    assert len(filtered) < len(unfiltered)


def test_citation_to_a_rejected_chunk_is_not_verifiable() -> None:
    """
    A rejected chunk cannot be verified as a source.

    _extract_citations keeps every citation the model emitted but marks
    unmatched ones found_in_context=False rather than dropping them. Because
    filtering now happens before generation, a rejected chunk is absent from
    the context set, so any citation naming it can never verify.

    Note this is the pre-existing contract: an unverifiable citation still
    reaches the response. Blocking or repairing those is the Citation
    Verifier's job (agent #9), not this fix's.
    """
    chunks = drop_filtered_chunks(
        [
            _chunk("kept-doc", filtered_out=False, index=4),
            _chunk("rejected-doc", filtered_out=True, index=9),
        ]
    )
    answer = "Setbacks are 5 ft [kept-doc, chunk 4] and 10 ft [rejected-doc, chunk 9]."
    by_doc = {c["doc_id"]: c for c in _extract_citations(answer, chunks)}

    assert by_doc["kept-doc"]["found_in_context"] is True
    assert by_doc["rejected-doc"]["found_in_context"] is False
