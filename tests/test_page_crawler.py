"""
tests/test_page_crawler.py — Unit tests for ingestion/page_crawler.py

Link discovery uses inline HTML (no network). SSRF validation mocks DNS
resolution so tests never resolve real hosts.
"""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import pytest

from ingestion.page_crawler import (
    MAX_LINKS_PER_PAGE,
    AssetLink,
    discover_asset_links,
    validate_pull_url,
)

PAGE_URL = "https://city.gov/building/forms"


def _public_ips(host, port):
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


def _discover(html: str) -> list[AssetLink]:
    with patch("socket.getaddrinfo", side_effect=_public_ips):
        return discover_asset_links(PAGE_URL, html=html)


# ════════════════════════════════════════════════
#  validate_pull_url (SSRF guard)
# ════════════════════════════════════════════════


def test_rejects_http():
    with pytest.raises(ValueError, match="https"):
        validate_pull_url("http://city.gov/page")


def test_rejects_localhost():
    with pytest.raises(ValueError):
        validate_pull_url("https://localhost/admin")


def test_rejects_private_ip():
    with pytest.raises(ValueError, match="blocked"):
        validate_pull_url("https://192.168.1.10/internal")


def test_rejects_metadata_ip():
    with pytest.raises(ValueError, match="blocked"):
        validate_pull_url("https://169.254.169.254/latest/meta-data")


def test_rejects_loopback_ip():
    with pytest.raises(ValueError, match="blocked"):
        validate_pull_url("https://127.0.0.1/x")


def test_rejects_host_resolving_private():
    def private_ips(host, port):
        return [(2, 1, 6, "", ("10.0.0.5", 0))]

    with patch("socket.getaddrinfo", side_effect=private_ips):
        with pytest.raises(ValueError, match="blocked"):
            validate_pull_url("https://sneaky.example.com/doc.pdf")


def test_accepts_public_https_host():
    with patch("socket.getaddrinfo", side_effect=_public_ips):
        validate_pull_url("https://city.gov/building/forms")  # no raise


# ════════════════════════════════════════════════
#  discover_asset_links
# ════════════════════════════════════════════════


def test_finds_supported_extensions():
    html = """
    <html><body>
      <a href="/files/permit.pdf">Permit</a>
      <a href="guide.docx">Guide</a>
      <a href="slides.pptx">Slides</a>
      <a href="notes.txt">Notes</a>
      <a href="readme.md">Readme</a>
      <a href="page.html">Page</a>
    </body></html>
    """
    links = _discover(html)
    assert [l.extension for l in links] == [
        ".pdf", ".docx", ".pptx", ".txt", ".md", ".html",
    ]


def test_skips_unsupported_and_nonfile_links():
    html = """
    <a href="/files/permit.pdf">ok</a>
    <a href="/about">page without extension</a>
    <a href="archive.zip">zip</a>
    <a href="mailto:permits@city.gov">mail</a>
    <a href="javascript:void(0)">js</a>
    <a href="#section">anchor</a>
    <a href="tel:+12145551212">phone</a>
    """
    links = _discover(html)
    assert len(links) == 1
    assert links[0].url == "https://city.gov/files/permit.pdf"


def test_resolves_relative_urls_against_page():
    html = '<a href="../fees/schedule.pdf">Fees</a>'
    links = _discover(html)
    assert links[0].url == "https://city.gov/fees/schedule.pdf"
    assert links[0].url_normalized == "https://city.gov/fees/schedule.pdf"


def test_dedupes_by_normalized_url():
    html = """
    <a href="/files/doc.pdf">one</a>
    <a href="https://city.gov/files/doc.pdf#page=2">two</a>
    <a href="HTTPS://CITY.GOV/files/doc.pdf?utm_source=x">three</a>
    """
    links = _discover(html)
    assert len(links) == 1


def test_sets_normalized_filename():
    html = '<a href="/files/Pool_Permit Guide-v2.pdf">Guide</a>'
    links = _discover(html)
    assert links[0].filename == "pool-permit-guide.pdf"


def test_truncates_at_max_links():
    anchors = "".join(
        f'<a href="/f/doc{i}.pdf">d{i}</a>' for i in range(MAX_LINKS_PER_PAGE + 10)
    )
    links = _discover(anchors)
    assert len(links) == MAX_LINKS_PER_PAGE


def test_page_url_itself_is_validated():
    with pytest.raises(ValueError):
        discover_asset_links("https://localhost/forms", html="<a href='a.pdf'>x</a>")


def test_fetch_rejects_non_html_page():
    with patch("socket.getaddrinfo", side_effect=_public_ips), patch(
        "ingestion.harvester.fetch_document",
        return_value=(b"%PDF-1.7", None, None, "application/pdf"),
    ):
        with pytest.raises(ValueError, match="HTML page"):
            discover_asset_links("https://city.gov/direct.pdf")
