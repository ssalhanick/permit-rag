"""
audit/provenance.py — what corpus state produced an answer
===========================================================
A trace says *how much* an answer cost. Provenance says *what it was built
from*: which chunks, from which document versions, at which checksums, with
which document_status, under which prompt fragment versions.

This matters because the corpus is mutable by design. Documents get
superseded, repealed, re-pulled, and re-chunked (see ingestion/governance.py).
Six months after the fact, "why did it say that?" is unanswerable without a
snapshot of what was current at answer time -- the chunk may now belong to a
superseded version, or have been re-chunked out of existence.

Two consumers:
  - the superadmin dashboard, as the evidence behind an action item
  - the Performance Review agent, which cannot attribute a bad answer to
    retrieval vs. generation without knowing what retrieval actually returned

Import boundary: audit/ -> db/, standard library only (AGENTS.md).

Usage:
    from audit.provenance import capture_provenance, snapshot_to_evidence

    snap = capture_provenance(chunks, prompt_version="v1")
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkProvenance:
    """One retrieved chunk, pinned to the document state that produced it."""

    doc_id: str
    chunk_index: int | None
    municipality: str | None
    authority_level: str | None
    document_status: str | None
    checksum_sha256: str | None
    effective_date: str | None
    similarity: float | None
    reranked_score: float | None
    retrieval_weight: float | None
    filtered_out: bool


@dataclass
class ProvenanceSnapshot:
    """Everything needed to reconstruct why an answer said what it said."""

    captured_at: str
    prompt_version: str | None = None
    prompt_fragment_ids: list[str] = field(default_factory=list)
    persona: str | None = None
    jurisdiction: str | None = None
    chunks: list[ChunkProvenance] = field(default_factory=list)

    @property
    def doc_ids(self) -> list[str]:
        """Distinct documents that contributed, in first-seen order."""
        seen: set[str] = set()
        out: list[str] = []
        for chunk in self.chunks:
            if chunk.doc_id not in seen:
                seen.add(chunk.doc_id)
                out.append(chunk.doc_id)
        return out

    @property
    def superseded_doc_ids(self) -> list[str]:
        """
        Documents that were not 'active' at answer time.

        AGENTS.md forbids a superseded document being the sole source of an
        answer; this is the field that makes that auditable after the fact.
        """
        return sorted(
            {
                c.doc_id
                for c in self.chunks
                if c.document_status and c.document_status != "active"
            }
        )

    @property
    def is_solely_superseded(self) -> bool:
        """True when every contributing document was non-active."""
        if not self.chunks:
            return False
        return len(self.superseded_doc_ids) == len(self.doc_ids)


def _as_float(value: Any) -> float | None:
    """Coerce to float, or None when absent/unparseable."""
    if isinstance(value, int | float):
        return float(value)
    return None


def capture_provenance(
    chunks: list[dict[str, Any]],
    *,
    prompt_version: str | None = None,
    prompt_fragment_ids: list[str] | None = None,
    persona: str | None = None,
    jurisdiction: str | None = None,
) -> ProvenanceSnapshot:
    """
    Snapshot the corpus state behind a set of retrieved chunks.

    Records filtered_out chunks too. They did not reach the model, but knowing
    what the reranker rejected is exactly what you need when diagnosing a
    "why didn't it find X" complaint.
    """
    captured = [
        ChunkProvenance(
            doc_id=str(c.get("doc_id") or "unknown"),
            chunk_index=c.get("chunk_index"),
            municipality=c.get("municipality"),
            authority_level=c.get("authority_level"),
            document_status=c.get("document_status"),
            checksum_sha256=c.get("checksum_sha256"),
            effective_date=str(c["effective_date"]) if c.get("effective_date") else None,
            similarity=_as_float(c.get("similarity")),
            reranked_score=_as_float(c.get("reranked_score")),
            retrieval_weight=_as_float(c.get("retrieval_weight")),
            filtered_out=bool(c.get("filtered_out", False)),
        )
        for c in chunks
    ]
    return ProvenanceSnapshot(
        captured_at=datetime.now(UTC).isoformat(),
        prompt_version=prompt_version,
        prompt_fragment_ids=list(prompt_fragment_ids or []),
        persona=persona,
        jurisdiction=jurisdiction,
        chunks=captured,
    )


def snapshot_to_evidence(snapshot: ProvenanceSnapshot) -> dict[str, Any]:
    """
    Render a snapshot as the `evidence` jsonb payload of an action item.

    Kept compact: per-chunk detail is summarised rather than inlined whole,
    because an action item is read by a human in a queue, not replayed.
    """
    return {
        "captured_at": snapshot.captured_at,
        "prompt_version": snapshot.prompt_version,
        "prompt_fragment_ids": snapshot.prompt_fragment_ids,
        "persona": snapshot.persona,
        "jurisdiction": snapshot.jurisdiction,
        "doc_ids": snapshot.doc_ids,
        "superseded_doc_ids": snapshot.superseded_doc_ids,
        "chunk_count": len(snapshot.chunks),
        "chunks_prompted": sum(1 for c in snapshot.chunks if not c.filtered_out),
        "chunks": [asdict(c) for c in snapshot.chunks[:20]],
    }
