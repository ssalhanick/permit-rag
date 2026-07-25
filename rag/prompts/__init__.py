"""
rag/prompts/ — the versioned prompt-fragment library (Phase 4)
==============================================================
The Prompt Router (``rag/agents/prompt_router.py``) composes a system prompt per
request from small, hand-authored fragments instead of one unversioned blob.
This package is the fragment *store*: it loads the fragment files, tracks each
one's version, and offers the two mechanical helpers the router needs
(``get_fragment`` and ``bound_notes``). The *selection* logic — which persona,
which default, how big ``max_tokens`` should be — lives in the router, not here.

**Fragments are files, not database rows.** Each lives at
``rag/prompts/fragments/<dimension>/<key>.md`` (except ``base.md``), is
git-tracked, and carries its own version in a ``<!-- version: N -->`` header on
the first line. That is what makes iteration measurable: edit a fragment, bump
its header, and every trace and eval run records the new ``dimension:key@version``
id (``prompt_fragment_ids`` on ``agent_steps``, migration 026). A quality shift
is then attributable to an exact fragment set.

Dimensions: ``base`` (a single frozen fragment), ``persona``, ``jurisdiction``,
``intent``, ``experience``.

Import boundary: rag/ → db/, audit/, standard library only (AGENTS.md). This
package imports none of those — it only reads its own files.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_FRAGMENTS_DIR = Path(__file__).parent / "fragments"
_VERSION_RE = re.compile(r"^\s*<!--\s*version:\s*(\d+)\s*-->\s*$", re.IGNORECASE)

# Every dimension that lives in its own subdirectory. ``base`` is a lone file.
DIMENSIONS: tuple[str, ...] = ("persona", "jurisdiction", "intent", "experience")

# ~4 chars per token is the standard rough estimate; the router never bills off
# this — it is only used to bound untrusted project notes before composition.
_CHARS_PER_TOKEN = 4
DEFAULT_NOTES_MAX_TOKENS = 200


@dataclass(frozen=True)
class Fragment:
    """One composable prompt fragment, with the version it was authored at."""

    dimension: str
    key: str
    version: int
    body: str

    @property
    def id(self) -> str:
        """Trace/eval identity, e.g. ``persona:diy@1``. Recorded on every step."""
        return f"{self.dimension}:{self.key}@{self.version}"


def _parse(path: Path, *, dimension: str, key: str) -> Fragment:
    """Read a fragment file, split its version header from the body."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    version = 1
    if lines and (m := _VERSION_RE.match(lines[0])):
        version = int(m.group(1))
        lines = lines[1:]
    return Fragment(dimension=dimension, key=key, version=version, body="\n".join(lines).strip())


@lru_cache(maxsize=1)
def _load_all() -> dict[tuple[str, str], Fragment]:
    """Load every fragment file once. Keyed by ``(dimension, key)``."""
    store: dict[tuple[str, str], Fragment] = {}
    base_path = _FRAGMENTS_DIR / "base.md"
    if base_path.exists():
        store[("base", "base")] = _parse(base_path, dimension="base", key="base")
    for dimension in DIMENSIONS:
        d = _FRAGMENTS_DIR / dimension
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            key = path.stem
            store[(dimension, key)] = _parse(path, dimension=dimension, key=key)
    return store


def get_fragment(dimension: str, key: str | None) -> Fragment | None:
    """Return the fragment for ``(dimension, key)``, or None when absent.

    A None or unknown ``key`` returns None so the router can log a
    ``fragment_missing`` gap (a Crystallizer input) and fall back — a missing
    fragment is never fatal.
    """
    if not key:
        return None
    return _load_all().get((dimension, key))


def base_fragment() -> Fragment:
    """Return the frozen base fragment (the grounding rules; the cache prefix)."""
    frag = _load_all().get(("base", "base"))
    if frag is None:  # pragma: no cover — the file is shipped with the package
        raise RuntimeError("rag/prompts/fragments/base.md is missing")
    return frag


def keys_for(dimension: str) -> list[str]:
    """Every authored key in a dimension, sorted. Used by tests and the router."""
    return sorted(k for (d, k) in _load_all() if d == dimension)


@lru_cache(maxsize=1)
def library_version() -> str:
    """A short stable digest over every fragment id.

    Changes whenever any fragment's version header changes, so a single value on
    a trace answers "which library built this?" without listing every id.
    """
    ids = sorted(frag.id for frag in _load_all().values())
    digest = hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()
    return f"lib-{digest[:12]}"


def bound_notes(text: str | None, *, max_tokens: int = DEFAULT_NOTES_MAX_TOKENS) -> str:
    """Sanitize and length-bound untrusted project notes for safe composition.

    Project notes are user/LLM-authored free text placed LAST in the system
    prompt. They are bounded (≈``max_tokens``) and stripped of the control and
    markup characters that could break out of their block or forge a new prompt
    section. This is defense in depth, not a guarantee — the notes still sit
    after the grounding rules, which the base fragment marks as non-overridable.
    """
    if not text:
        return ""
    cleaned = text.replace("\r", "\n")
    # Drop control chars except newline/tab; collapse runs of blank lines.
    cleaned = "".join(c for c in cleaned if c == "\n" or c == "\t" or c.isprintable())
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(cleaned) <= max_chars:
        return cleaned
    # Truncate on a word boundary within the budget, never mid-word.
    head = cleaned[:max_chars]
    if " " in head:
        head = head[: head.rindex(" ")]
    return head.rstrip() + " …"
