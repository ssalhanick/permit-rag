"""
rag/agents/citation_verifier.py — Citation Verifier (agent #9)
==============================================================
Phase 5 answer-path agent. AGENTS.md requires every generated answer to carry a
citation; this agent checks that each *cited* claim is actually supported by the
chunk it points at, and flags claims that carry no citation at all. A confident
sentence with a fabricated or mismatched citation is the most dangerous failure
in a compliance tool — it looks authoritative and is wrong.

**Deterministic span-match first, LLM entailment on the leftovers** (arch): most
citations are verifiable by token overlap — the claim's salient words appear in
the chunk it cites. That is free and needs no model. Only the sentences whose
overlap is ambiguous go to a single batched entailment call. A citation that
points at a chunk retrieval never returned is unsupported outright (no model
needed — the evidence does not exist).

Never raises and never rewrites the answer: it returns a verdict the Manager /
Guardrail / Evaluator read. Import boundary: rag/agents/ → rag/, db/, audit/,
standard library. Every model call goes through ``run_agent``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from rag.agent_runtime import Tier, run_agent

log = logging.getLogger(__name__)

AGENT_NAME = "citation_verifier"

# "[doc-id, chunk 3]" or "[doc-id chunk 3]" — the generator's inline citation.
_CITATION_RE = re.compile(r"\[([^\]]+?)[,\s]+chunk\s*(\d+)\]", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "must", "your", "you",
    "are", "which", "will", "have", "has", "may", "can", "any", "all", "not",
    "when", "where", "shall", "should", "into", "within", "per", "chunk",
})
# Overlap at/above this ⇒ supported deterministically; below ⇒ ask the model.
_SPAN_FLOOR = 0.6


class _Entailment(BaseModel):
    """One leftover claim's entailment verdict."""

    index: int = Field(description="Position in the leftovers list.")
    supported: bool = Field(description="Does the cited chunk support the claim?")


class _EntailmentBatch(BaseModel):
    """The model's verdicts for every ambiguous claim in one call."""

    verdicts: list[_Entailment] = Field(default_factory=list)


@dataclass
class ClaimCheck:
    """One sentence's citation verdict."""

    sentence: str
    citation: str | None  # "doc_id chunk N", or None when uncited
    verdict: str  # 'supported' | 'unsupported' | 'uncited'
    method: str  # 'span' | 'entailment' | 'missing_chunk' | 'none'


@dataclass
class VerificationResult:
    """The Citation Verifier's report over one answer."""

    claims: list[ClaimCheck] = field(default_factory=list)

    @property
    def cited(self) -> list[ClaimCheck]:
        """Claims that carried a citation (the ones precision is measured over)."""
        return [c for c in self.claims if c.citation is not None]

    @property
    def unsupported(self) -> list[ClaimCheck]:
        """Cited claims whose evidence did not hold up."""
        return [c for c in self.cited if c.verdict == "unsupported"]

    @property
    def uncited(self) -> list[ClaimCheck]:
        """Factual-looking sentences with no citation at all."""
        return [c for c in self.claims if c.verdict == "uncited"]

    @property
    def citation_precision(self) -> float:
        """Share of cited claims that are supported (1.0 when nothing is cited)."""
        cited = self.cited
        if not cited:
            return 1.0
        return sum(c.verdict == "supported" for c in cited) / len(cited)


def _salient(text: str) -> set[str]:
    """Content tokens of a string: alnum words ≥3 chars, minus stopwords."""
    return {w for w in _WORD_RE.findall(text.lower()) if len(w) >= 3 and w not in _STOPWORDS}


def _chunk_index(chunks: list[dict[str, Any]]) -> dict[tuple[str, int], str]:
    """Map (doc_id, chunk_index) → chunk text for citation lookup."""
    return {
        (str(c.get("doc_id")), int(c.get("chunk_index", -1))): str(c.get("content", ""))
        for c in chunks
    }


def _looks_factual(sentence: str) -> bool:
    """A sentence worth citing — long enough and not a pure hedge/heading."""
    return len(_salient(sentence)) >= 4


def _span_verdict(sentence: str, chunk_text: str) -> bool | None:
    """Deterministic overlap check: True/False, or None if ambiguous (ask LLM)."""
    claim_terms = _salient(re.sub(_CITATION_RE, "", sentence))
    if not claim_terms:
        return True
    overlap = len(claim_terms & _salient(chunk_text)) / len(claim_terms)
    if overlap >= _SPAN_FLOOR:
        return True
    if overlap <= 0.2:
        return False
    return None  # middling — a paraphrase the model should judge


def _classify_sentences(
    answer: str, index: dict[tuple[str, int], str]
) -> tuple[list[ClaimCheck], list[tuple[int, str, str]]]:
    """First pass: deterministic verdicts + a list of leftovers for the model."""
    claims: list[ClaimCheck] = []
    leftovers: list[tuple[int, str, str]] = []  # (claim_idx, sentence, chunk_text)
    for raw in _SENTENCE_RE.split(answer.strip()):
        sentence = raw.strip()
        if not sentence:
            continue
        m = _CITATION_RE.search(sentence)
        if not m:
            verdict = "uncited" if _looks_factual(sentence) else "supported"
            claims.append(ClaimCheck(sentence, None, verdict, "none"))
            continue
        key = (m.group(1).strip(), int(m.group(2)))
        citation = f"{key[0]} chunk {key[1]}"
        chunk_text = index.get(key)
        if chunk_text is None:
            claims.append(ClaimCheck(sentence, citation, "unsupported", "missing_chunk"))
            continue
        span = _span_verdict(sentence, chunk_text)
        if span is None:
            leftovers.append((len(claims), sentence, chunk_text))
            claims.append(ClaimCheck(sentence, citation, "unsupported", "entailment"))
        else:
            claims.append(ClaimCheck(sentence, citation, "supported" if span else "unsupported", "span"))
    return claims, leftovers


def _entail(leftovers: list[tuple[int, str, str]], client: Any | None) -> _EntailmentBatch:
    """One batched entailment call over the ambiguous cited claims."""
    body = "\n".join(
        f"[{i}] CLAIM: {s}\n    CHUNK: {t[:600]}" for i, (_, s, t) in enumerate(leftovers)
    )
    result = run_agent(
        AGENT_NAME,
        system=(
            "For each numbered CLAIM, decide whether the CHUNK's text supports it. "
            "Return one verdict per index. 'supported' means the chunk states or "
            "directly implies the claim; a topic match is not enough."
        ),
        messages=[{"role": "user", "content": body}],
        tier=Tier.MID,  # entailment is a sonnet-class judgement (arch cost table)
        output_format=_EntailmentBatch,
        max_tokens=512,
        temperature=0.0,
        input_parts=tuple(s for _, s, _ in leftovers),
        client=client,
    )
    return result.parsed_output


def verify_answer(
    answer: str,
    chunks: list[dict[str, Any]],
    *,
    use_llm: bool = True,
    client: Any | None = None,
) -> VerificationResult:
    """Verify every cited claim in an answer against its chunk.

    Deterministic span match first; the ambiguous leftovers go to one batched
    entailment call (skipped when ``use_llm=False`` — they stay 'unsupported',
    the conservative default). Never raises.
    """
    claims, leftovers = _classify_sentences(answer or "", _chunk_index(chunks))
    if leftovers and use_llm:
        try:
            batch = _entail(leftovers, client)
            resolved = {v.index: v.supported for v in batch.verdicts}
            for i, (claim_idx, _, _) in enumerate(leftovers):
                if resolved.get(i):
                    claims[claim_idx].verdict = "supported"
        except Exception as exc:  # a verifier failure must not break the answer
            log.warning("citation entailment failed, leaving leftovers unsupported: %s", exc)
    return VerificationResult(claims=claims)
