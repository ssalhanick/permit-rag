"""
tests/test_url_normalize.py — Unit tests for ingestion/url_normalize.py

Covers normalize_source_url and normalize_filename per the rules in
docs/on_demand_url_pull.md. Pure functions — no DB, no network.
"""

from __future__ import annotations

import pytest

from ingestion.url_normalize import normalize_filename, normalize_source_url


# ════════════════════════════════════════════════
#  normalize_source_url
# ════════════════════════════════════════════════


def test_lowercases_scheme_and_host():
    assert (
        normalize_source_url("HTTPS://City.GOV/Building/Forms.PDF")
        == "https://city.gov/Building/Forms.PDF"
    )


def test_forces_https_for_http():
    assert (
        normalize_source_url("http://city.gov/doc.pdf")
        == "https://city.gov/doc.pdf"
    )


def test_strips_fragment():
    assert (
        normalize_source_url("https://city.gov/doc.pdf#page=3")
        == "https://city.gov/doc.pdf"
    )


def test_strips_tracking_params_keeps_real_ones():
    url = "https://city.gov/doc?utm_source=x&id=7&gclid=abc&fbclid=z&mc_cid=9"
    assert normalize_source_url(url) == "https://city.gov/doc?id=7"


def test_resolves_relative_against_base():
    assert (
        normalize_source_url("../files/permit.pdf", base_url="https://city.gov/building/forms/")
        == "https://city.gov/building/files/permit.pdf"
    )


def test_resolves_root_relative_against_base():
    assert (
        normalize_source_url("/files/permit.pdf", base_url="https://city.gov/building/forms")
        == "https://city.gov/files/permit.pdf"
    )


def test_collapses_duplicate_slashes():
    assert (
        normalize_source_url("https://city.gov//building///forms/doc.pdf")
        == "https://city.gov/building/forms/doc.pdf"
    )


def test_strips_trailing_slash_but_keeps_root():
    assert normalize_source_url("https://city.gov/forms/") == "https://city.gov/forms"
    assert normalize_source_url("https://city.gov/") == "https://city.gov/"
    assert normalize_source_url("https://city.gov") == "https://city.gov/"


def test_drops_default_ports():
    assert normalize_source_url("http://city.gov:80/a") == "https://city.gov/a"
    assert normalize_source_url("https://city.gov:443/a") == "https://city.gov/a"


def test_same_doc_different_noise_normalizes_equal():
    a = normalize_source_url("HTTP://City.gov/forms/doc.pdf?utm_campaign=fall#top")
    b = normalize_source_url("https://city.gov//forms/doc.pdf")
    assert a == b


def test_raises_on_relative_url_without_base():
    with pytest.raises(ValueError):
        normalize_source_url("files/doc.pdf")


# ════════════════════════════════════════════════
#  normalize_filename
# ════════════════════════════════════════════════


def test_filename_lowercased():
    assert normalize_filename("Permit-Guide.PDF") == "permit-guide.pdf"


def test_filename_strips_query_noise():
    assert normalize_filename("doc.pdf?ver=3") == "doc.pdf"


def test_filename_strips_version_suffix():
    assert normalize_filename("permit-guide-v2.pdf") == "permit-guide.pdf"


def test_filename_strips_copy_number():
    assert normalize_filename("permit-guide (1).pdf") == "permit-guide.pdf"


def test_filename_strips_date_suffix():
    assert normalize_filename("fee-schedule-2024-03.pdf") == "fee-schedule.pdf"


def test_filename_strips_copy_word():
    assert normalize_filename("checklist copy.pdf") == "checklist.pdf"


def test_filename_takes_last_path_segment():
    assert normalize_filename("https://city.gov/a/b/doc.pdf") == "doc.pdf"
    assert normalize_filename("a\\b\\doc.pdf") == "doc.pdf"


def test_filename_collapses_underscores_and_spaces():
    assert normalize_filename("Pool_Permit  Guide.pdf") == "pool-permit-guide.pdf"


def test_filename_stacked_suffixes():
    assert normalize_filename("guide-v2 (3).pdf") == "guide.pdf"


def test_filename_keeps_extension():
    assert normalize_filename("form.docx") == "form.docx"


def test_filename_no_extension_ok():
    assert normalize_filename("README") == "readme"
