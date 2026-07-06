"""
evaluation/prod_preflight.py — Production RDS corpus checks before RAGAs eval
==============================================================================
Verifies ENVIRONMENT=production, DATABASE_URL points at RDS, and the corpus
has documents with embeddings before running ``evaluation.ragas_eval``.

Import boundary: evaluation/ → db/, rag/, audit/, standard library only (AGENTS.md).

Usage:
    $env:ENVIRONMENT="production"
    py -m evaluation.prod_preflight
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIN_ACTIVE_DOCS = 1
DEFAULT_MIN_EMBEDDED_CHUNKS = 1
EXPECTED_ACTIVE_DOCS = 10
EXPECTED_EMBEDDED_CHUNKS = 7000


@dataclass(frozen=True)
class CorpusCounts:
    """Document and chunk counts read from the connected database."""

    documents: int
    active_documents: int
    chunks: int
    embedded_chunks: int


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of a production corpus preflight run."""

    ok: bool
    profile: str
    database_url_masked: str
    counts: CorpusCounts | None
    messages: list[str]


def bootstrap_eval_env() -> str:
    """Load dotenv files for the active profile. Returns ``local`` or ``production``."""
    if os.environ.get("AWS_EXECUTION_ENV") or os.environ.get("ECS_CONTAINER_METADATA_URI_V4"):
        profile = "production"
    else:
        explicit = os.environ.get("ENVIRONMENT", "").strip().lower()
        if explicit in {"production", "prod"}:
            profile = "production"
        elif explicit in {"local", "development", "dev"}:
            profile = "local"
        else:
            profile = "local"

    if profile == "local":
        load_dotenv(PROJECT_ROOT / ".env.local", override=True)
    else:
        prod_file = PROJECT_ROOT / ".env.production"
        if prod_file.exists():
            load_dotenv(prod_file, override=True)

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    os.environ.setdefault("ENVIRONMENT", profile)
    return profile


def mask_database_url(db_url: str) -> str:
    """Return a password-redacted DATABASE_URL safe for logs."""
    if not db_url or "@" not in db_url:
        return db_url or "NOT SET"
    scheme_prefix = ""
    rest = db_url
    if "://" in db_url:
        scheme, rest = db_url.split("://", 1)
        scheme_prefix = f"{scheme}://"
    creds, host = rest.split("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme_prefix}{user}:***@{host}"


def validate_production_rds() -> list[str]:
    """Return error messages when the session is not pointed at production RDS."""
    errors: list[str] = []
    profile = os.environ.get("ENVIRONMENT", "").strip().lower()
    if profile not in {"production", "prod"}:
        errors.append('Set ENVIRONMENT=production before running prod preflight.')

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        errors.append("DATABASE_URL is not set (see .env.production).")
    elif "localhost" in db_url or "127.0.0.1" in db_url:
        errors.append("DATABASE_URL must point at production RDS, not localhost.")
    elif "rds.amazonaws.com" not in db_url:
        errors.append("DATABASE_URL does not look like an AWS RDS endpoint.")
    return errors


def fetch_corpus_counts(conn: Any) -> CorpusCounts:
    """Query document and chunk counts using dict-row cursors."""
    documents = conn.execute("SELECT COUNT(1) AS n FROM documents").fetchone()["n"]
    active_documents = conn.execute(
        "SELECT COUNT(1) AS n FROM documents WHERE document_status = %s",
        ("active",),
    ).fetchone()["n"]
    chunks = conn.execute("SELECT COUNT(1) AS n FROM chunks").fetchone()["n"]
    embedded_chunks = conn.execute(
        "SELECT COUNT(1) AS n FROM chunks WHERE embedding IS NOT NULL"
    ).fetchone()["n"]
    return CorpusCounts(
        documents=int(documents),
        active_documents=int(active_documents),
        chunks=int(chunks),
        embedded_chunks=int(embedded_chunks),
    )


def run_preflight(
    *,
    min_active_docs: int = DEFAULT_MIN_ACTIVE_DOCS,
    min_embedded_chunks: int = DEFAULT_MIN_EMBEDDED_CHUNKS,
) -> PreflightResult:
    """Check production RDS connectivity and corpus readiness for RAGAs eval."""
    profile = bootstrap_eval_env()
    messages: list[str] = []
    validation_errors = validate_production_rds()
    db_url = os.environ.get("DATABASE_URL", "")
    masked = mask_database_url(db_url)

    if validation_errors:
        messages.extend(validation_errors)
        return PreflightResult(
            ok=False,
            profile=profile,
            database_url_masked=masked,
            counts=None,
            messages=messages,
        )

    from db.client import get_conn

    try:
        with get_conn() as conn:
            counts = fetch_corpus_counts(conn)
    except Exception as exc:
        messages.append(f"Database connection failed: {exc}")
        return PreflightResult(
            ok=False,
            profile=profile,
            database_url_masked=masked,
            counts=None,
            messages=messages,
        )

    messages.append(f"DATABASE_URL → {masked}")
    messages.append(
        "Corpus counts: "
        f"documents={counts.documents}, active={counts.active_documents}, "
        f"chunks={counts.chunks}, embedded={counts.embedded_chunks}"
    )

    if counts.active_documents < min_active_docs:
        messages.append(
            f"FAIL: active documents {counts.active_documents} < required {min_active_docs}."
        )
    if counts.embedded_chunks < min_embedded_chunks:
        messages.append(
            f"FAIL: embedded chunks {counts.embedded_chunks} < required {min_embedded_chunks}."
        )

    if counts.active_documents < EXPECTED_ACTIVE_DOCS:
        messages.append(
            f"WARN: active documents {counts.active_documents} < expected {EXPECTED_ACTIVE_DOCS}."
        )
    if counts.embedded_chunks < EXPECTED_EMBEDDED_CHUNKS:
        messages.append(
            f"WARN: embedded chunks {counts.embedded_chunks} < expected {EXPECTED_EMBEDDED_CHUNKS}."
        )

    ok = (
        counts.active_documents >= min_active_docs
        and counts.embedded_chunks >= min_embedded_chunks
    )
    if ok:
        messages.append("PASS: production corpus is ready for RAGAs eval.")

    return PreflightResult(
        ok=ok,
        profile=profile,
        database_url_masked=masked,
        counts=counts,
        messages=messages,
    )


def main() -> None:
    """CLI entrypoint for production corpus preflight."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = run_preflight()
    for line in result.messages:
        log.info(line)
    if not result.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
