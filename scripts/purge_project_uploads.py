"""
scripts/purge_project_uploads.py — Purge project-upload docs via admin API
==========================================================================

Usage:
    py -m scripts.purge_project_uploads --doc-id my-project-doc-1
    py -m scripts.purge_project_uploads --doc-id-file docs_to_purge.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


def load_doc_ids(doc_ids: list[str], doc_id_file: str | None) -> list[str]:
    """Return unique doc_ids from args and optional file."""
    values: list[str] = [item.strip() for item in doc_ids if item.strip()]
    if doc_id_file:
        lines = Path(doc_id_file).read_text(encoding="utf-8").splitlines()
        values.extend(line.strip() for line in lines if line.strip() and not line.strip().startswith("#"))
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def resolve_admin_token(cli_token: str | None) -> str:
    """Resolve admin token from CLI flag or environment."""
    token = (cli_token or os.environ.get("API_ADMIN_TOKEN", "")).strip()
    if not token:
        raise RuntimeError("API_ADMIN_TOKEN is empty. Set it in .env or pass --admin-token.")
    return token


def build_purge_request(api_base_url: str, doc_id: str, token: str, role: str) -> Request:
    """Build HTTP request object for purge endpoint."""
    endpoint = f"{api_base_url.rstrip('/')}/admin/documents/{doc_id}/purge-project-upload"
    return Request(
        endpoint,
        method="POST",
        headers={
            "X-Admin-Token": token,
            "X-Admin-Role": role,
        },
    )


def purge_one(api_base_url: str, doc_id: str, token: str, role: str) -> tuple[bool, str]:
    """Call purge endpoint once and return success flag plus message."""
    request = build_purge_request(api_base_url, doc_id, token, role)
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return True, str(payload.get("message", "purged"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body or str(exc)
        return False, f"HTTP {exc.code}: {detail}"
    except URLError as exc:
        return False, f"Network error: {exc.reason}"


def run_purge(api_base_url: str, doc_ids: Iterable[str], token: str, role: str) -> int:
    """Run purge for all doc_ids and return process exit code."""
    failures: list[tuple[str, str]] = []
    for doc_id in doc_ids:
        ok, message = purge_one(api_base_url, doc_id, token, role)
        marker = "OK" if ok else "FAIL"
        print(f"[{marker}] {doc_id} -> {message}")
        if not ok:
            failures.append((doc_id, message))
    if failures:
        print(f"\nFailed: {len(failures)}")
        return 1
    print("\nAll purge calls succeeded.")
    return 0


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for purge script."""
    parser = argparse.ArgumentParser(description="Purge source_tier=3 project uploads via admin API.")
    parser.add_argument("--doc-id", action="append", default=[], help="Doc ID to purge (repeatable).")
    parser.add_argument("--doc-id-file", default=None, help="Text file with one doc_id per line.")
    parser.add_argument("--api-base-url", default=os.environ.get("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--admin-token", default=None, help="Admin token override (else .env API_ADMIN_TOKEN).")
    parser.add_argument(
        "--admin-role",
        default=os.environ.get("API_PURGE_ADMIN_ROLE") or os.environ.get("API_ADMIN_ROLE", "admin"),
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    load_dotenv()
    args = parse_args()
    doc_ids = load_doc_ids(args.doc_id, args.doc_id_file)
    if not doc_ids:
        print("No doc_ids provided. Use --doc-id or --doc-id-file.")
        return 2
    token = resolve_admin_token(args.admin_token)
    return run_purge(args.api_base_url, doc_ids, token, args.admin_role)


if __name__ == "__main__":
    sys.exit(main())
