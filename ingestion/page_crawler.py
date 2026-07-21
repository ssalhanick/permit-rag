"""
ingestion/page_crawler.py — Single-page asset link discovery
=============================================================
On-demand URL pull feature (docs/on_demand_url_pull.md).

Public API:
    validate_pull_url(url) -> None            (raises ValueError — SSRF guard)
    discover_asset_links(page_url, html=None) -> list[AssetLink]

Fetches one admin-supplied page (via harvester.fetch_document — HTTP stays
in the harvester), parses anchors with BeautifulSoup, and returns de-duped
links to supported file types. Single page only — no recursion, no watching.

Import boundary: ingestion/ → db/, standard library only (AGENTS.md);
bs4/requests third-party deps are shared with chunker/harvester.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from ingestion.url_normalize import normalize_filename, normalize_source_url

log = logging.getLogger(__name__)

# File types the ingest pipeline can extract today (plan: Format support).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".html", ".htm", ".txt", ".md"}

# Abuse guards
MAX_LINKS_PER_PAGE = 50
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB per-file cap (enforced by caller)


@dataclass(frozen=True)
class AssetLink:
    """One downloadable file discovered on a pulled page."""
    url: str             # absolute, as found on the page
    url_normalized: str  # identity key (ingestion/url_normalize.py)
    filename: str        # normalized base filename (fallback identity)
    extension: str       # lowercase, with leading dot


# ════════════════════════════════════════════════
#  SSRF GUARD
# ════════════════════════════════════════════════


def _resolved_ips(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve *host* to IP addresses. Raises ValueError if unresolvable."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host {host!r}: {exc}") from exc
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def validate_pull_url(url: str) -> None:
    """
    Reject URLs unsafe to fetch server-side (SSRF guard).

    Raises ValueError unless the URL is https, resolves publicly, and is
    not localhost / private / link-local / reserved / cloud-metadata.
    Call again on the final URL after redirects.
    """
    parts = urlsplit(url)
    if parts.scheme.lower() != "https":
        raise ValueError(f"Only https URLs are allowed, got {parts.scheme!r}")

    host = parts.hostname or ""
    if not host:
        raise ValueError(f"URL has no host: {url!r}")
    if host.lower() in {"localhost", "metadata.google.internal"}:
        raise ValueError(f"Host {host!r} is not allowed")

    for ip in _resolved_ips(host):
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(f"Host {host!r} resolves to blocked address {ip}")


def fetch_asset(
    url: str,
    *,
    timeout: int = 30,
    max_redirects: int = 5,
    max_bytes: int = MAX_FILE_BYTES,
) -> tuple[bytes, str]:
    """
    Download one asset with SSRF re-validation on every redirect hop.

    Returns (content_bytes, content_type).
    Raises ValueError on unsafe URL, oversized file, or redirect loop;
    requests.HTTPError on non-200.
    """
    import requests

    from ingestion.harvester import HEADERS

    current = url
    for _ in range(max_redirects + 1):
        validate_pull_url(current)
        resp = requests.get(
            current, headers=HEADERS, timeout=timeout, allow_redirects=False
        )
        if resp.is_redirect or resp.is_permanent_redirect:
            current = urljoin(current, resp.headers.get("Location", ""))
            continue
        resp.raise_for_status()
        if len(resp.content) > max_bytes:
            raise ValueError(
                f"File exceeds {max_bytes} byte cap: {url} ({len(resp.content)} bytes)"
            )
        return resp.content, resp.headers.get("Content-Type", "")
    raise ValueError(f"Too many redirects fetching {url}")


# ════════════════════════════════════════════════
#  LINK DISCOVERY
# ════════════════════════════════════════════════


def _extension_of(url: str) -> str:
    """Return the lowercase file extension of a URL path ('' if none)."""
    path = urlsplit(url).path
    name = path.rsplit("/", 1)[-1]
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()


def discover_asset_links(page_url: str, html: str | None = None) -> list[AssetLink]:
    """
    Fetch *page_url* (unless *html* is provided) and return supported
    file links, de-duped by normalized URL, in page order.

    Raises ValueError on SSRF-unsafe page URL; requests errors propagate.
    """
    validate_pull_url(page_url)

    if html is None:
        from ingestion.harvester import fetch_document

        content, _etag, _lm, content_type = fetch_document(page_url)
        if "html" not in (content_type or "").lower():
            raise ValueError(
                f"Pull target must be an HTML page, got Content-Type {content_type!r}"
            )
        html = content.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "html.parser")
    links: list[AssetLink] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
            continue

        absolute = urljoin(page_url, href)
        ext = _extension_of(absolute)
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        try:
            normalized = normalize_source_url(absolute, base_url=page_url)
        except ValueError:
            log.warning("Skipping unparseable link %r on %s", href, page_url)
            continue

        if normalized in seen:
            continue
        seen.add(normalized)

        links.append(
            AssetLink(
                url=absolute,
                url_normalized=normalized,
                filename=normalize_filename(absolute),
                extension=ext,
            )
        )
        if len(links) >= MAX_LINKS_PER_PAGE:
            log.warning(
                "Page %s exceeded %d supported links — truncating",
                page_url, MAX_LINKS_PER_PAGE,
            )
            break

    log.info("discover_asset_links: %s → %d supported links", page_url, len(links))
    return links
