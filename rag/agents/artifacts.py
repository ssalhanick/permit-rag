"""
rag/agents/artifacts.py — the artifact store
=============================================
Phase 2 of the agent architecture. Agents pass :class:`ArtifactRef` — an id, a
kind, a one-line summary, a token count, and a TTL — never raw text. The payload
itself lives in an :class:`ArtifactStore` and is resolved only at the boundary
where a step actually needs it.

**This is what bounds the Manager's context.** A ReAct loop resends everything
accumulated so far on every iteration, so a Manager that carried retrieved chunk
text would pay for that text once per iteration — a 6-iteration loop over
top_k=10 chunks costs more than the generation it is orchestrating. Carrying
``"chunks: 10 chunks / 4 docs / top_sim 0.88"`` instead makes the loop's context
roughly constant regardless of corpus size. It is also why the Manager cannot
accidentally leak superseded or reranker-rejected text into a prompt: it never
holds the text at all.

Token counts here are a **deterministic estimate**, not a bill. Real billing is
whatever ``client.messages.count_tokens`` and the API's usage block report, both
of which live in ``rag/agent_runtime.py``. The estimate exists so the Budget
Governor can make a cap decision without a network round trip per candidate
plan; it is documented as approximate and never written to a trace as usage.

Import boundary: rag/agents/ → rag/, db/, audit/, standard library (AGENTS.md).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# Average characters per token for English prose plus code-ish metadata headers.
# Claude's tokenizer is not public; 4.0 is the conventional approximation and is
# deliberately a slight *under*-estimate of token count for dense text, which is
# why the Budget Governor treats a near-cap estimate as over-cap.
_CHARS_PER_TOKEN = 4.0

DEFAULT_TTL_SECONDS = 900  # 15 minutes — longer than any single request


class ExpiredArtifactError(KeyError):
    """Raised when a ref is resolved after its TTL has elapsed."""


class MissingArtifactError(KeyError):
    """Raised when a ref names an artifact this store never held."""


@dataclass(frozen=True)
class ArtifactRef:
    """
    A handle to a stored artifact. This — not the payload — is what agents pass.

    Args:
        id: Opaque unique id, also what lands in ``agent_steps.artifact_refs``.
        kind: What the payload is ("chunks", "answer", "conflicts", ...). The
            Manager routes on kind, so it must be stable vocabulary.
        summary: One line a model can reason over without the payload.
        token_count: Estimated tokens the payload would cost if inlined. See the
            module docstring — an estimate, never a bill.
        ttl: Seconds the artifact stays resolvable, from ``created_at``.
        created_at: Monotonic timestamp captured at ``put`` time.
    """

    id: str
    kind: str
    summary: str
    token_count: int
    ttl: int = DEFAULT_TTL_SECONDS
    created_at: float = field(default_factory=time.monotonic)

    def is_expired(self, *, now: float | None = None) -> bool:
        """True when this ref's TTL has elapsed."""
        return (now if now is not None else time.monotonic()) - self.created_at > self.ttl

    def describe(self) -> str:
        """Render the ref the way a Manager prompt would see it."""
        return f"[{self.kind}:{self.id}] {self.summary} (~{self.token_count} tok)"


def estimate_tokens(payload: Any) -> int:
    """
    Deterministic token estimate for a payload, for cap decisions only.

    Strings measure directly; lists and dicts measure their rendered length.
    Never used for cost accounting — ``rag/agent_runtime.py`` owns that, and it
    uses the real counter (AGENTS.md forbids a tiktoken guess in the paid path).
    """
    if payload is None:
        return 0
    if isinstance(payload, str):
        chars = len(payload)
    elif isinstance(payload, list | tuple):
        chars = sum(len(str(item)) for item in payload)
    elif isinstance(payload, dict):
        chars = sum(len(str(k)) + len(str(v)) for k, v in payload.items())
    else:
        chars = len(str(payload))
    return int(chars / _CHARS_PER_TOKEN)


class ArtifactStore:
    """
    Per-run payload storage behind :class:`ArtifactRef` handles.

    Scoped to one request. Nothing here is durable — provenance (which corpus
    state produced an answer) is ``audit/provenance.py``'s job, not this one's.
    """

    def __init__(self, *, default_ttl: int = DEFAULT_TTL_SECONDS) -> None:
        """Create an empty store whose refs default to ``default_ttl`` seconds."""
        self._payloads: dict[str, Any] = {}
        self._refs: dict[str, ArtifactRef] = {}
        self._default_ttl = default_ttl

    def put(
        self,
        kind: str,
        payload: Any,
        *,
        summary: str,
        token_count: int | None = None,
        ttl: int | None = None,
    ) -> ArtifactRef:
        """Store a payload and return the ref that stands in for it."""
        ref = ArtifactRef(
            id=f"{kind}-{uuid.uuid4().hex[:12]}",
            kind=kind,
            summary=summary,
            token_count=estimate_tokens(payload) if token_count is None else token_count,
            ttl=self._default_ttl if ttl is None else ttl,
        )
        self._payloads[ref.id] = payload
        self._refs[ref.id] = ref
        return ref

    def get(self, ref: ArtifactRef | str) -> Any:
        """
        Resolve a ref to its payload.

        Raises ``MissingArtifactError`` for an unknown id and ``ExpiredArtifactError``
        once the TTL has elapsed — an expired ref must fail loudly rather than
        resolve to stale context.
        """
        ref_id = ref.id if isinstance(ref, ArtifactRef) else ref
        stored = self._refs.get(ref_id)
        if stored is None:
            raise MissingArtifactError(ref_id)
        if stored.is_expired():
            raise ExpiredArtifactError(ref_id)
        return self._payloads[ref_id]

    def get_or_none(self, ref: ArtifactRef | str | None) -> Any:
        """Resolve a ref, returning None for a missing, expired, or null ref."""
        if ref is None:
            return None
        try:
            return self.get(ref)
        except KeyError:
            return None

    def refs(self) -> list[ArtifactRef]:
        """Every ref this store has issued, in insertion order."""
        return list(self._refs.values())

    def ref_ids(self) -> list[str]:
        """Every issued ref id — the shape ``agent_steps.artifact_refs`` wants."""
        return list(self._refs)

    def total_tokens(self) -> int:
        """Estimated tokens across every stored artifact."""
        return sum(ref.token_count for ref in self._refs.values())

    def __len__(self) -> int:
        """Number of artifacts held."""
        return len(self._refs)
