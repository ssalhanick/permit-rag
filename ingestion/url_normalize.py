"""
ingestion/url_normalize.py — Shared URL + filename normalization
=================================================================
On-demand URL pull feature (docs/on_demand_url_pull.md).

Single source of truth for document identity keys:
    normalize_source_url(url, base_url=None) -> str
    normalize_filename(name) -> str

Used by BOTH the harvester and the pull route. Store the normalized
value in the DB (`source_url_normalized`, `source_filename`); never
normalize ad hoc at query time.

Import boundary: ingestion/ → db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Tracking params stripped from query strings (prefix match).
_TRACKING_PREFIXES = ("utm_", "mc_")
_TRACKING_EXACT = {"gclid", "fbclid", "msclkid", "igshid"}

# Filename noise: version/date/copy suffixes stripped by normalize_filename.
_FILENAME_NOISE = re.compile(
    r"""
    (
        [-_\s]?v\d+                    # -v2, _v10
      | [-_\s]?\d{4}[-_]\d{2}([-_]\d{2})?  # -2024-03, -2024-03-15
      | \s*\(\d+\)                     # (1), (2)
      | [-_\s]copy                     # copy suffix
      | [-_\s]final                    # final suffix
    )+$
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _strip_tracking_params(query: str) -> str:
    """Remove utm_*, mc_*, gclid, fbclid, etc. from a query string."""
    pairs = parse_qsl(query, keep_blank_values=True)
    kept = [
        (k, v)
        for k, v in pairs
        if k.lower() not in _TRACKING_EXACT
        and not k.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlencode(kept)


def normalize_source_url(url: str, base_url: str | None = None) -> str:
    """
    Return the canonical identity form of *url* for document matching.

    Rules (docs/on_demand_url_pull.md):
        - resolve relative URLs against *base_url* (the page URL)
        - lowercase scheme + host
        - force https scheme for comparison
        - strip fragment (#...)
        - strip tracking params (utm_*, mc_*, gclid, fbclid)
        - collapse duplicate slashes in the path
        - strip trailing slash (except root path)

    Raises ValueError if no absolute URL can be produced.
    """
    candidate = url.strip()
    if base_url:
        candidate = urljoin(base_url.strip(), candidate)

    parts = urlsplit(candidate)
    if not parts.scheme or not parts.netloc:
        raise ValueError(f"Cannot normalize non-absolute URL: {url!r}")

    scheme = parts.scheme.lower()
    if scheme in ("http", "https"):
        scheme = "https"

    host = parts.netloc.lower()
    # Drop default ports
    if host.endswith(":80") or host.endswith(":443"):
        host = host.rsplit(":", 1)[0]

    # Collapse duplicate slashes; strip trailing slash except root.
    # (Dot segments are already resolved by urljoin when base_url is given.)
    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query = _strip_tracking_params(parts.query)

    return urlunsplit((scheme, host, path, query, ""))


def normalize_filename(name: str) -> str:
    """
    Return the canonical base filename for fallback identity matching.

    Rules:
        - take the last path segment, drop any query string
        - lowercase
        - strip version/date/copy suffixes (-v2, (1), -2024-03, ' copy', -final)
        - collapse whitespace/underscores to single hyphens
        - keep the extension
    """
    base = name.strip().split("?", 1)[0].split("#", 1)[0]
    base = base.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    base = base.lower()

    if "." in base:
        stem, ext = base.rsplit(".", 1)
        ext = "." + ext
    else:
        stem, ext = base, ""

    stem = _FILENAME_NOISE.sub("", stem).strip()
    stem = re.sub(r"[\s_]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")

    return f"{stem}{ext}"
