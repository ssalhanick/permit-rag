"""
ingestion/verification.py — Ingestion stage verification
=========================================================
Runs at every ingestion stage — no silent failures (AGENTS.md).
Writes results to both the database (ingestion_verifications table)
and a local registry.json per document.

Stages: download → extraction → chunking → embedding

Usage:
    from ingestion.verification import verify_download, verify_extraction,
        verify_chunking, verify_embedding, run_full_verification
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

log = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────
MIN_FILE_SIZE_BYTES = 500          # below this → likely a redirect/error page
MIN_EXTRACTED_CHARS = 100          # below this → likely scanned or empty
COVERAGE_RATIO_THRESHOLD = 0.80   # chunking must cover ≥80% of source chars
MIN_CHUNKS_PER_DOC = 1            # at least 1 chunk per document

# Where results are persisted alongside metadata
REGISTRY_DIR = Path("documents/metadata")


# ════════════════════════════════════════════════
#  RESULT DATACLASS
# ════════════════════════════════════════════════

class VerificationResult:
    """Structured result from a verification check."""

    def __init__(
        self,
        stage: str,
        result: str,
        detail: dict[str, Any],
        doc_id: str,
    ):
        self.stage = stage
        self.result = result       # pass | fail | skip | needs_ocr
        self.detail = detail
        self.doc_id = doc_id

    @property
    def passed(self) -> bool:
        """True if result is 'pass'."""
        return self.result == "pass"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON / database storage."""
        return {
            "stage": self.stage,
            "result": self.result,
            "detail": self.detail,
            "doc_id": self.doc_id,
        }

    def __repr__(self) -> str:
        status = "✅" if self.passed else "❌"
        return f"{status} {self.stage}: {self.result} ({self.doc_id})"


# ════════════════════════════════════════════════
#  STAGE: DOWNLOAD
# ════════════════════════════════════════════════

def verify_download(
    doc_id: str,
    raw_path: Path,
    expected_checksum: str | None = None,
) -> VerificationResult:
    """
    Verify a downloaded file exists, is non-trivial, and
    optionally matches an expected SHA-256 checksum.
    """
    detail: dict[str, Any] = {"raw_path": str(raw_path)}

    if not raw_path.exists():
        detail["error"] = "File not found"
        return VerificationResult("download", "fail", detail, doc_id)

    file_size = raw_path.stat().st_size
    detail["file_size_bytes"] = file_size

    if file_size < MIN_FILE_SIZE_BYTES:
        detail["error"] = (
            f"File too small ({file_size} bytes < "
            f"{MIN_FILE_SIZE_BYTES} minimum)"
        )
        return VerificationResult("download", "fail", detail, doc_id)

    # Compute checksum
    sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    detail["checksum_sha256"] = sha

    if expected_checksum and sha != expected_checksum:
        detail["error"] = "Checksum mismatch"
        detail["expected_checksum"] = expected_checksum
        return VerificationResult("download", "fail", detail, doc_id)

    log.info("Download verified: %s (%d bytes)", doc_id, file_size)
    return VerificationResult("download", "pass", detail, doc_id)


# ════════════════════════════════════════════════
#  STAGE: EXTRACTION
# ════════════════════════════════════════════════

def verify_extraction(
    doc_id: str,
    raw_chars: int,
    is_scanned: bool = False,
) -> VerificationResult:
    """
    Verify that text extraction produced meaningful content.

    Flags scanned PDFs as needs_ocr rather than fail.
    """
    detail: dict[str, Any] = {"raw_chars": raw_chars}

    if is_scanned:
        detail["error"] = "Scanned PDF — OCR required"
        log.warning("Extraction needs OCR: %s", doc_id)
        return VerificationResult(
            "extraction", "needs_ocr", detail, doc_id
        )

    if raw_chars < MIN_EXTRACTED_CHARS:
        detail["error"] = (
            f"Too few chars extracted ({raw_chars} < "
            f"{MIN_EXTRACTED_CHARS} minimum)"
        )
        return VerificationResult("extraction", "fail", detail, doc_id)

    log.info("Extraction verified: %s (%d chars)", doc_id, raw_chars)
    return VerificationResult("extraction", "pass", detail, doc_id)


# ════════════════════════════════════════════════
#  STAGE: CHUNKING
# ════════════════════════════════════════════════

def verify_chunking(
    doc_id: str,
    source_chars: int,
    chunks: list[dict[str, Any]],
) -> VerificationResult:
    """
    Verify that chunking produced a reasonable set of chunks
    with adequate coverage of the source text.
    """
    num_chunks = len(chunks)
    chunk_chars = sum(c.get("char_count", 0) for c in chunks)

    # Coverage ratio: total chunk chars / source chars
    # Can exceed 1.0 due to overlap, that's fine
    coverage = chunk_chars / source_chars if source_chars > 0 else 0.0

    detail: dict[str, Any] = {
        "source_chars": source_chars,
        "chunk_chars": chunk_chars,
        "num_chunks": num_chunks,
        "coverage_ratio": round(coverage, 4),
    }

    if num_chunks < MIN_CHUNKS_PER_DOC:
        detail["error"] = f"Too few chunks ({num_chunks})"
        return VerificationResult("chunking", "fail", detail, doc_id)

    if coverage < COVERAGE_RATIO_THRESHOLD:
        detail["error"] = (
            f"Low coverage ({coverage:.2%} < "
            f"{COVERAGE_RATIO_THRESHOLD:.0%} threshold)"
        )
        return VerificationResult("chunking", "fail", detail, doc_id)

    log.info(
        "Chunking verified: %s — %d chunks, %.1f%% coverage",
        doc_id, num_chunks, coverage * 100,
    )
    return VerificationResult("chunking", "pass", detail, doc_id)


# ════════════════════════════════════════════════
#  STAGE: EMBEDDING
# ════════════════════════════════════════════════

def verify_embedding(
    doc_id: str,
    num_chunks: int,
    num_embedded: int,
    embedding_dim: int = 768,
) -> VerificationResult:
    """
    Verify that all chunks received embeddings and
    the embedding dimensions match expectations.
    """
    detail: dict[str, Any] = {
        "num_chunks": num_chunks,
        "num_embedded": num_embedded,
        "embedding_dim": embedding_dim,
    }

    if num_embedded < num_chunks:
        detail["error"] = (
            f"Missing embeddings: {num_embedded}/{num_chunks} "
            f"chunks embedded"
        )
        return VerificationResult("embedding", "fail", detail, doc_id)

    if embedding_dim != 768:
        detail["error"] = (
            f"Unexpected embedding dim: {embedding_dim} (expected 768)"
        )
        return VerificationResult("embedding", "fail", detail, doc_id)

    log.info(
        "Embedding verified: %s — %d/%d chunks",
        doc_id, num_embedded, num_chunks,
    )
    return VerificationResult("embedding", "pass", detail, doc_id)


# ════════════════════════════════════════════════
#  PERSISTENCE: write to registry.json
# ════════════════════════════════════════════════

def save_verification_to_registry(
    result: VerificationResult,
    registry_dir: Path | None = None,
) -> None:
    """
    Append a verification result to the document's metadata
    JSON sidecar in documents/metadata/{doc_id}.json.

    Per AGENTS.md: "Verification results written to registry.json
    per document."
    """
    if registry_dir is None:
        registry_dir = REGISTRY_DIR

    sidecar_path = registry_dir / f"{result.doc_id}.json"

    if sidecar_path.exists():
        data = json.loads(sidecar_path.read_text())
    else:
        data = {"doc_id": result.doc_id}

    # Store verifications as a dict keyed by stage
    verifications = data.get("verifications", {})
    verifications[result.stage] = {
        "result": result.result,
        "detail": result.detail,
    }
    data["verifications"] = verifications

    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(json.dumps(data, indent=2))

    log.info(
        "Saved verification to %s: %s=%s",
        sidecar_path.name, result.stage, result.result,
    )


# ════════════════════════════════════════════════
#  PERSISTENCE: write to database
# ════════════════════════════════════════════════

def save_verification_to_db(
    result: VerificationResult,
    document_id: UUID,
) -> None:
    """
    Write a verification result to the ingestion_verifications
    table via db/client.py.

    Requires a running database connection.
    """
    from db.client import insert_verification

    insert_verification(
        document_id=document_id,
        stage=result.stage,
        result=result.result,
        detail=result.detail,
    )


# ════════════════════════════════════════════════
#  COMBINED RUNNER
# ════════════════════════════════════════════════

def run_full_verification(
    doc_id: str,
    raw_path: Path,
    raw_chars: int,
    clean_chars: int,
    chunks: list[dict[str, Any]],
    is_scanned: bool = False,
    expected_checksum: str | None = None,
    document_id: UUID | None = None,
    save_to_db: bool = False,
) -> list[VerificationResult]:
    """
    Run download + extraction + chunking verification in sequence.

    Stops at the first failure and returns all results so far.
    Optionally persists results to the database if document_id
    and save_to_db are provided.

    Returns a list of VerificationResult objects.
    """
    results: list[VerificationResult] = []

    # 1. Download
    dl = verify_download(doc_id, raw_path, expected_checksum)
    results.append(dl)
    save_verification_to_registry(dl)
    if save_to_db and document_id:
        save_verification_to_db(dl, document_id)
    if not dl.passed:
        log.error("Download verification failed for %s — aborting", doc_id)
        return results

    # 2. Extraction
    ext = verify_extraction(doc_id, raw_chars, is_scanned)
    results.append(ext)
    save_verification_to_registry(ext)
    if save_to_db and document_id:
        save_verification_to_db(ext, document_id)
    if not ext.passed:
        log.error("Extraction verification failed for %s — aborting", doc_id)
        return results

    # 3. Chunking
    chk = verify_chunking(doc_id, clean_chars, chunks)
    results.append(chk)
    save_verification_to_registry(chk)
    if save_to_db and document_id:
        save_verification_to_db(chk, document_id)
    if not chk.passed:
        log.error("Chunking verification failed for %s — aborting", doc_id)
        return results

    log.info("All verifications passed for %s", doc_id)
    return results


# ════════════════════════════════════════════════
#  SUMMARY REPORT
# ════════════════════════════════════════════════

def print_verification_summary(
    results: list[VerificationResult],
) -> None:
    """Print a human-readable summary of verification results."""
    print(f"\n{'─'*50}")
    print("  Verification Summary")
    print(f"{'─'*50}")

    for r in results:
        emoji = {"pass": "✅", "fail": "❌", "needs_ocr": "🔍", "skip": "⏭️"}
        icon = emoji.get(r.result, "❓")
        print(f"  {icon} {r.stage:<12} {r.result:<10} {r.doc_id}")
        if "error" in r.detail:
            print(f"     └─ {r.detail['error']}")

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n  {passed}/{total} stages passed")
    print(f"{'─'*50}\n")
