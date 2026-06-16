"""
rag/conflict_detector.py — Lightweight conflict detection (Sprint 5 / Task 15)
================================================================================
Scoped implementation: detects when two or more retrieved chunks from DIFFERENT
authority levels appear to address the same subject but state different
numeric or conditional requirements.

Detection strategy (Tier A — lightweight):
  1. Build a subject keyword index from the retrieved chunks.
  2. For each subject that appears in ≥2 chunks from different authority levels,
     extract numeric values (feet, sq ft, %, stories, etc.) from each chunk.
  3. If the numeric values differ, emit a ConflictWarning.

This is intentionally conservative — it only flags clear numeric discrepancies
to avoid false positives. Section normalization and full content diff
(Task 13, Sprint 7) is a future enhancement.

Import boundary: rag/ → standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


# ── Subject vocabulary ────────────────────────────────────────
# Subjects where conflicting numeric requirements are most meaningful.

_SUBJECT_PATTERNS: dict[str, list[str]] = {
    "setback": ["setback", "set back", "set-back"],
    "height limit": ["height limit", "maximum height", "max height", "building height"],
    "lot coverage": ["lot coverage", "impervious cover", "floor area ratio", "far "],
    "fence height": ["fence height", "wall height", "fence permit"],
    "fire separation": ["fire separation", "fire-rated", "separation distance"],
    "unit density": ["units per acre", "dwelling unit", "density"],
    "sprinkler": ["sprinkler", "fire suppression", "nfpa 13"],
    "parking ratio": ["parking space", "parking ratio", "parking requirement"],
    "egress": ["egress width", "means of egress", "exit width"],
}

# Regex to extract a leading numeric value from a sentence
_NUMERIC_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*"
    r"(?:feet|foot|ft|inches|in\.|stories|story|percent|%|sq\.?\s*ft|acres?|spaces?)",
    re.IGNORECASE,
)

# Authority level hierarchy (higher index = higher authority)
_AUTHORITY_ORDER = {"federal": 3, "state": 2, "county": 1, "municipal": 0}


# ── Result type ───────────────────────────────────────────────


@dataclass
class ConflictResult:
    """A detected conflict between two chunks."""

    subject: str
    chunk_a: dict[str, Any]
    chunk_b: dict[str, Any]
    detail: str


# ── Core detection ────────────────────────────────────────────


def _extract_numeric_values(text: str, subject_keywords: list[str]) -> list[str]:
    """
    Return numeric value strings found near a subject keyword in text.
    Searches up to 300 chars around each keyword match.
    """
    lower = text.lower()
    values: list[str] = []
    for kw in subject_keywords:
        idx = lower.find(kw)
        while idx != -1:
            window = text[max(0, idx - 50): idx + 300]
            hits = _NUMERIC_RE.findall(window)
            values.extend(hits)
            idx = lower.find(kw, idx + 1)
    return list(set(values))


def _chunks_cover_subject(chunk: dict[str, Any], keywords: list[str]) -> bool:
    """Return True if the chunk content mentions any of the subject keywords."""
    lower = str(chunk.get("content", "")).lower()
    return any(kw in lower for kw in keywords)


def detect_conflicts(chunks: list[dict[str, Any]]) -> list[ConflictResult]:
    """
    Detect lightweight numeric conflicts between chunks from different authority levels.

    Args:
        chunks: Retrieved chunks (passing_chunks only — filtered_out=False).

    Returns:
        List of ConflictResult objects. May be empty.
    """
    conflicts: list[ConflictResult] = []
    passing = [c for c in chunks if not c.get("filtered_out", False)]

    for subject, keywords in _SUBJECT_PATTERNS.items():
        # Collect chunks that mention this subject
        subject_chunks = [c for c in passing if _chunks_cover_subject(c, keywords)]
        if len(subject_chunks) < 2:
            continue

        # Group by authority level
        by_authority: dict[str, list[dict[str, Any]]] = {}
        for c in subject_chunks:
            auth = str(c.get("authority_level") or "unknown").lower()
            by_authority.setdefault(auth, []).append(c)

        if len(by_authority) < 2:
            continue  # all chunks have the same authority level → no cross-level conflict

        # Compare pairs across different authority levels
        authority_list = list(by_authority.items())
        for i in range(len(authority_list)):
            auth_a, group_a = authority_list[i]
            for j in range(i + 1, len(authority_list)):
                auth_b, group_b = authority_list[j]

                chunk_a = group_a[0]
                chunk_b = group_b[0]

                vals_a = _extract_numeric_values(str(chunk_a.get("content", "")), keywords)
                vals_b = _extract_numeric_values(str(chunk_b.get("content", "")), keywords)

                if not vals_a or not vals_b:
                    continue  # can't compare without numeric values

                # Check for any value in vals_a that does not appear in vals_b
                a_set = set(vals_a)
                b_set = set(vals_b)
                if a_set == b_set:
                    continue  # values agree

                detail = (
                    f"'{subject}' — {auth_a.upper()} source states {sorted(a_set)} "
                    f"but {auth_b.upper()} source states {sorted(b_set)}. "
                    f"The {_higher_authority(auth_a, auth_b).upper()} source typically "
                    f"sets the floor; verify with the AHJ."
                )
                log.info(
                    "conflict detected: subject='%s' docs=%s vs %s",
                    subject,
                    chunk_a.get("doc_id"),
                    chunk_b.get("doc_id"),
                )
                conflicts.append(
                    ConflictResult(
                        subject=subject,
                        chunk_a=chunk_a,
                        chunk_b=chunk_b,
                        detail=detail,
                    )
                )

    return conflicts


def _higher_authority(auth_a: str, auth_b: str) -> str:
    """Return the authority level string with higher precedence."""
    rank_a = _AUTHORITY_ORDER.get(auth_a.lower(), 0)
    rank_b = _AUTHORITY_ORDER.get(auth_b.lower(), 0)
    return auth_a if rank_a >= rank_b else auth_b
