"""
tests/test_prompt_router.py — the Prompt Router (agent #2, Phase 4).

Covers the four things the router must get right, each a documented requirement:
  * an absent/unknown persona resolves to ``research`` — NEVER ``diy``,
  * composition is base ∥ persona ∥ jurisdiction ∥ intent ∥ experience ∥ notes,
  * a requested-but-missing fragment is recorded, never fatal,
  * ``max_tokens`` is persona/intent-aware (killing the hard-coded 1024),
  * project notes are bounded and placed last.

Pure: no database, no API key, no network. The fragment files ship with the
package, so the loader reads real content.
"""

from __future__ import annotations

import pytest

from rag import prompts
from rag.agents.prompt_router import (
    DEFAULT_PERSONA,
    EXPERIENCES,
    INTENTS,
    PERSONAS,
    max_tokens_for,
    route,
)

# ── The research default (never diy) ─────────────────────────


def test_absent_persona_resolves_to_research_not_diy() -> None:
    routed = route(persona=None)
    assert routed.persona == "research" == DEFAULT_PERSONA
    assert routed.persona != "diy"
    assert routed.persona_defaulted is True


def test_unknown_persona_resolves_to_research() -> None:
    routed = route(persona="wizard")
    assert routed.persona == "research"
    assert routed.persona_defaulted is True


def test_known_persona_is_used_and_not_flagged_as_default() -> None:
    routed = route(persona="diy")
    assert routed.persona == "diy"
    assert routed.persona_defaulted is False


@pytest.mark.parametrize(
    "stored, expected",
    [
        ("DIY", "diy"),
        (" diy ", "diy"),
        ("hiring-contractor", "hiring_contractor"),  # the kickoff hyphen bug
        ("Hiring-Contractor", "hiring_contractor"),
    ],
)
def test_persona_variants_normalize_and_route(stored: str, expected: str) -> None:
    """UI/legacy persona variants resolve to a known persona, not the research default."""
    routed = route(persona=stored)
    assert routed.persona == expected
    assert routed.persona_defaulted is False


# ── Composition ──────────────────────────────────────────────


def test_base_is_always_first_and_grounding_rules_present() -> None:
    routed = route(persona="contractor")
    assert routed.fragment_ids[0].startswith("base:base@")
    # The non-negotiable grounding rule survives from the base fragment.
    assert "ONLY the provided source chunks" in routed.system


def test_composition_order_places_persona_before_intent() -> None:
    routed = route(persona="diy", jurisdiction="dallas", intent="how_to", experience="first_timer")
    ids = list(routed.fragment_ids)
    order = [i.split("@")[0] for i in ids]
    assert order == [
        "base:base", "persona:diy", "jurisdiction:dallas",
        "intent:how_to", "experience:first_timer",
    ]


def test_fort_worth_alias_maps_to_fragment() -> None:
    routed = route(persona="research", jurisdiction="Fort Worth")
    assert any(i.startswith("jurisdiction:fort_worth@") for i in routed.fragment_ids)


def test_fortworth_corpus_spelling_maps_to_fragment() -> None:
    """Regression guard: 'fortworth' (no separator) is the real seeded jurisdiction
    id (db/seeds/jurisdictions.sql) — a different string from 'ftworth', which was
    already aliased. Before this alias existed, this spelling fell through to the
    no-op slug fallback and never matched fort_worth.md."""
    routed = route(persona="research", jurisdiction="fortworth")
    assert any(i.startswith("jurisdiction:fort_worth@") for i in routed.fragment_ids)
    assert "jurisdiction:fortworth" not in routed.missing


def test_missing_fragment_is_recorded_not_fatal() -> None:
    routed = route(persona="research", jurisdiction="Nowhereville")
    assert "jurisdiction:nowhereville" in routed.missing
    # base + persona + intent still composed.
    assert routed.system
    assert any(i.startswith("persona:research@") for i in routed.fragment_ids)


def test_absent_optional_dimension_is_not_missing() -> None:
    # No jurisdiction / experience requested → not counted as missing.
    routed = route(persona="research")
    assert routed.missing == ()


# ── max_tokens sizing ────────────────────────────────────────


def test_diy_gets_a_larger_ceiling_than_contractor() -> None:
    assert max_tokens_for("diy", "compliance_lookup") > max_tokens_for("contractor", "compliance_lookup")


def test_hiring_contractor_clears_the_old_1024_cap() -> None:
    # The whole point: these personas truncated at 1024 before Phase 4.
    assert max_tokens_for("hiring_contractor", "compliance_lookup") > 1024
    assert max_tokens_for("diy", "how_to") > 1024


def test_verbose_intent_adds_headroom() -> None:
    assert max_tokens_for("diy", "how_to") > max_tokens_for("diy", "compliance_lookup")


def test_unknown_persona_sizing_falls_back_to_default() -> None:
    assert max_tokens_for("wizard", "compliance_lookup") == max_tokens_for(DEFAULT_PERSONA, "compliance_lookup")


def test_routed_max_tokens_matches_the_table() -> None:
    routed = route(persona="diy", intent="how_to")
    assert routed.max_tokens == max_tokens_for("diy", "how_to")


# ── Project notes: bounded, sanitized, last ──────────────────


def test_notes_are_composed_last_and_bounded() -> None:
    long_note = "cabinet swap. " * 200  # ~2800 chars, well over the budget
    routed = route(persona="research", project_notes=long_note)
    assert routed.fragment_ids[-1] == "project_notes"
    assert routed.system.rstrip().endswith("…")  # truncated marker
    assert "Project notes" in routed.system


def test_bound_notes_truncates_on_a_word_boundary() -> None:
    text = "word " * 500
    bounded = prompts.bound_notes(text, max_tokens=20)
    assert len(bounded) <= 20 * 4 + 2
    assert bounded.endswith("…")
    assert "wor" not in bounded.split()[-2:]  # no mid-word cut before the ellipsis


def test_bound_notes_empty_is_empty() -> None:
    assert prompts.bound_notes(None) == ""
    assert prompts.bound_notes("") == ""


# ── Library coverage + versioning ────────────────────────────


def test_every_persona_has_a_fragment() -> None:
    assert set(prompts.keys_for("persona")) == set(PERSONAS)


def test_every_intent_and_experience_has_a_fragment() -> None:
    assert set(prompts.keys_for("intent")) == set(INTENTS)
    assert set(prompts.keys_for("experience")) == set(EXPERIENCES)


def test_library_version_is_stable_and_tagged() -> None:
    v = prompts.library_version()
    assert v.startswith("lib-")
    assert v == prompts.library_version()  # deterministic
    assert route(persona="diy").library_version == v


def test_fragment_ids_carry_a_version() -> None:
    routed = route(persona="diy")
    assert all("@" in fid for fid in routed.fragment_ids if fid != "project_notes")
