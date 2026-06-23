"""
rag/permit_classifier.py — Multi-permit type classifier (Sprint 3 / Task 11)
==============================================================================
Classifies a natural-language project description into one or more of the nine
DFW permit types.

Strategy (two-tier with graceful fallback):

  Tier A — Zero-shot NLI (preferred):
    Model: cross-encoder/nli-deberta-v3-small (~85 MB, CPU-friendly)
    Hypothesis template: "This project requires a {type} permit."
    Entailment probability threshold: configurable via env
    PERMIT_CLASSIFIER_NLI_THRESHOLD (default 0.5)

  Tier B — Keyword fallback (always available):
    Applied when NLI is unavailable, slow-to-load, or confidence is below
    threshold for ALL types (acts as a safety net).
    Returns at least ["building"] for any construction-related description.

Usage:
    from rag.permit_classifier import classify_permit_types

    types = classify_permit_types("detached garage with a bathroom and 200-amp panel")
    # → ["building", "plumbing", "electrical"]

Import boundary: rag/ → standard library only (AGENTS.md).
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

# ── Permit type taxonomy ─────────────────────────────────────

PERMIT_TYPES: list[str] = [
    "building",
    "electrical",
    "plumbing",
    "mechanical",
    "zoning",
    "grading",
    "tree",
    "historic",
    "sign",
]

# ── Keyword rules (Tier B fallback) ─────────────────────────

KEYWORD_RULES: dict[str, list[str]] = {
    "building": [
        "construction", "addition", "demolition", "structure", "garage",
        "deck", "renovation", "remodel", "foundation", "framing", "roofing",
        "shed", "carport", "pergola", "porch", "room addition", "new build",
        "commercial build", "tenant improvement",
    ],
    "electrical": [
        "electrical", "panel", "wiring", "circuit", "ev charger", "outlet",
        "breaker", "generator", "solar", "photovoltaic", "pv system",
        "sub-panel", "amperage", "amp", "wire", "conduit",
    ],
    "plumbing": [
        "plumbing", "water heater", "fixture", "sewer", "drain",
        "bathroom", "toilet", "sink", "water line", "gas line",
        "sprinkler", "irrigation", "backflow", "septic",
    ],
    "mechanical": [
        "hvac", "duct", "ventilation", "furnace", "air handler",
        "air conditioner", "heat pump", "boiler", "exhaust fan",
        "mechanical", "cooling", "heating system",
    ],
    "zoning": [
        "setback", "variance", "lot coverage", "use change", "zoning",
        "rezoning", "special use", "conditional use", "overlay district",
        "density", "floor area ratio", "far",
    ],
    "grading": [
        "grading", "retaining wall", "earthwork", "drainage", "impervious",
        "cut and fill", "site work", "excavation", "slope", "culvert",
        "detention pond",
    ],
    "tree": [
        "tree", "protected tree", "landscape", "screening", "tree removal",
        "heritage tree", "canopy", "arborist", "tree preservation",
    ],
    "historic": [
        "historic", "conservation district", "preservation", "landmark",
        "historic district", "certificate of appropriateness", "demolition review",
    ],
    "sign": [
        "sign", "signage", "banner", "billboard", "awning sign",
        "monument sign", "pylon sign", "electronic sign",
    ],
}

# ── NLI hypothesis template ───────────────────────────────────

_NLI_HYPOTHESIS = "This project requires a {type} permit."
_NLI_MODEL_NAME = "cross-encoder/nli-deberta-v3-small"
_NLI_THRESHOLD_ENV = "PERMIT_CLASSIFIER_NLI_THRESHOLD"
_NLI_DEFAULT_THRESHOLD = 0.50

# Cached classifier instance (loaded once at first use)
_nli_classifier: object | None = None
_nli_available: bool | None = None   # True / False after first load attempt


def _get_nli_threshold() -> float:
    raw = os.environ.get(_NLI_THRESHOLD_ENV)
    if raw is None:
        return _NLI_DEFAULT_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return _NLI_DEFAULT_THRESHOLD


def _load_nli_classifier() -> object | None:
    """
    Load the HuggingFace zero-shot classifier once and cache it.

    Returns None if transformers is not installed or model cannot be loaded.
    """
    global _nli_classifier, _nli_available

    if _nli_available is True:
        return _nli_classifier
    if _nli_available is False:
        return None

    try:
        from transformers import pipeline  # type: ignore

        log.info("Loading NLI classifier: %s (first use — may download model)", _NLI_MODEL_NAME)
        _nli_classifier = pipeline(
            "zero-shot-classification",
            model=_NLI_MODEL_NAME,
            hypothesis_template=_NLI_HYPOTHESIS,
            device=-1,  # CPU — avoids CUDA dependency
        )
        _nli_available = True
        log.info("NLI classifier loaded successfully")
        return _nli_classifier
    except ImportError:
        log.warning(
            "transformers not installed — permit classifier will use keyword fallback only. "
            "Install with: pip install transformers torch"
        )
        _nli_available = False
        return None
    except Exception as exc:
        log.warning(
            "NLI classifier failed to load (%s) — falling back to keyword rules", exc
        )
        _nli_available = False
        return None


# ── Classification logic ─────────────────────────────────────


def _classify_keyword(description: str) -> list[str]:
    """
    Keyword-rule classifier (Tier B).

    Matches against KEYWORD_RULES using case-insensitive substring search.
    Always returns at least ["building"] for any non-empty description,
    since generic construction queries should surface building-permit results.
    """
    lower = description.lower()
    matched: list[str] = []
    for permit_type, keywords in KEYWORD_RULES.items():
        if any(kw in lower for kw in keywords):
            matched.append(permit_type)

    if not matched:
        log.debug("keyword classifier: no match — defaulting to ['building']")
        return ["building"]

    log.debug("keyword classifier matched: %s", matched)
    return matched


def _classify_nli(
    description: str,
    *,
    threshold: float,
) -> list[str] | None:
    """
    NLI zero-shot classifier (Tier A).

    Returns a list of permit types whose entailment probability >= threshold,
    or None if the classifier is unavailable.
    """
    clf = _load_nli_classifier()
    if clf is None:
        return None

    try:
        result = clf(description, PERMIT_TYPES, multi_label=True)
        # result["labels"] and result["scores"] are parallel lists
        labels: list[str] = result["labels"]
        scores: list[float] = result["scores"]

        matched = [
            label for label, score in zip(labels, scores)
            if score >= threshold
        ]
        log.debug(
            "NLI classifier: threshold=%.2f  matched=%s  scores=%s",
            threshold,
            matched,
            {l: f"{s:.3f}" for l, s in zip(labels, scores)},
        )
        return matched if matched else None
    except Exception as exc:
        log.warning("NLI inference failed (%s) — falling back to keyword rules", exc)
        return None


def classify_permit_types(
    description: str,
    *,
    use_nli: bool = True,
    threshold: float | None = None,
) -> list[str]:
    """
    Classify a project description into one or more permit types.

    Args:
        description: Free-text description of the project.
        use_nli:     If True (default), try the NLI model first.
                     Set to False to force keyword-only mode.
        threshold:   NLI entailment threshold (0-1). Defaults to env var
                     PERMIT_CLASSIFIER_NLI_THRESHOLD (default 0.5).

    Returns:
        Sorted list of permit type strings (e.g. ["building", "electrical"]).
        Always contains at least one element.

    Examples:
        >>> classify_permit_types("detached garage with bathroom and 200-amp panel")
        ['building', 'electrical', 'plumbing']

        >>> classify_permit_types("monument sign for a new retail store")
        ['building', 'sign']
    """
    if not description or not description.strip():
        log.warning("classify_permit_types: empty description — defaulting to ['building']")
        return ["building"]

    if threshold is None:
        threshold = _get_nli_threshold()

    # Tier A: NLI
    if use_nli:
        nli_result = _classify_nli(description, threshold=threshold)
        if nli_result is not None:
            # Fallback to keywords if NLI found nothing at this threshold
            if not nli_result:
                log.info(
                    "NLI found no types above threshold %.2f — "
                    "supplementing with keyword rules",
                    threshold,
                )
                return sorted(_classify_keyword(description))
            return sorted(nli_result)

    # Tier B: keyword fallback
    return sorted(_classify_keyword(description))


# ── Convenience: label for a single permit type ──────────────

_PERMIT_LABELS: dict[str, str] = {
    "building":    "Building / Structural",
    "electrical":  "Electrical",
    "plumbing":    "Plumbing",
    "mechanical":  "HVAC / Mechanical",
    "zoning":      "Zoning / Land Use",
    "grading":     "Grading / Site Work",
    "tree":        "Tree / Landscape",
    "historic":    "Historic Preservation",
    "sign":        "Sign",
}


def permit_type_label(permit_type: str) -> str:
    """Return a human-readable label for a permit type slug."""
    return _PERMIT_LABELS.get(permit_type, permit_type.replace("_", " ").title())
