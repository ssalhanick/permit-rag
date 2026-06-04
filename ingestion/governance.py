"""
ingestion/governance.py — Document-level change detection & supersession
=========================================================================
Sprint 3 / Task 9

Provides the re-scrape flow:
    download doc → compute SHA-256
        ├─ hash matches stored  → skip (log "no change")
        ├─ no stored hash       → ingest as new active document
        └─ hash differs         →
                ingest new doc (active, is_current=True)
                supersede old doc (superseded, is_current=False, superseded_by=new_id)
                re-chunk + re-embed new doc

Public API (called by ingestion/harvester.py and scripts):
    check_document_changed(doc_id, new_hash) -> ChangeStatus
    run_supersession_flow(old_doc_id, new_doc_id) -> dict
    rescrape_document(doc_id, catalog_entry, *, force=False) -> RescrapeResult

Import boundary: ingestion/ → db/, standard library only (AGENTS.md).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════
#  ENUMS & RESULT TYPES
# ════════════════════════════════════════════════


class ChangeStatus(Enum):
    """Result of comparing a new file hash to the stored document hash."""
    NO_CHANGE = "no_change"       # SHA-256 matches — skip ingest
    NEW_DOCUMENT = "new_document"  # No prior record — ingest fresh
    CHANGED = "changed"            # Hash differs — supersession flow


@dataclass
class RescrapeResult:
    """Outcome of a single-document re-scrape attempt."""
    doc_id: str
    status: Optional[ChangeStatus] = None
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    new_doc_id: Optional[str] = None   # set only when status == CHANGED
    superseded: bool = False
    error: Optional[str] = None
    messages: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return self.error is None

    def log_summary(self) -> None:
        icon = "✅" if self.ok() else "❌"
        log.info(
            "%s rescrape %s → %s  superseded=%s",
            icon, self.doc_id, self.status.value, self.superseded,
        )
        for msg in self.messages:
            log.info("    %s", msg)
        if self.error:
            log.error("    ERROR: %s", self.error)


# ════════════════════════════════════════════════
#  HASH HELPERS
# ════════════════════════════════════════════════


def sha256_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file without loading it all at once."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ════════════════════════════════════════════════
#  CHANGE DETECTION
# ════════════════════════════════════════════════


def check_document_changed(
    doc_id: str,
    new_hash: str,
) -> tuple[ChangeStatus, Optional[str]]:
    """
    Compare *new_hash* against what is stored in the DB for *doc_id*.

    Returns (ChangeStatus, stored_hash_or_None).
    """
    from db.client import get_document_by_doc_id

    existing = get_document_by_doc_id(doc_id)
    if existing is None:
        log.info("check_document_changed: %s — NEW (no DB record)", doc_id)
        return ChangeStatus.NEW_DOCUMENT, None

    stored_hash = existing.get("checksum_sha256")
    if not stored_hash:
        log.info(
            "check_document_changed: %s — treating as NEW (no stored hash)", doc_id
        )
        return ChangeStatus.NEW_DOCUMENT, None

    if stored_hash == new_hash:
        log.info("check_document_changed: %s — NO CHANGE", doc_id)
        return ChangeStatus.NO_CHANGE, stored_hash

    log.info(
        "check_document_changed: %s — CHANGED  old=%s…  new=%s…",
        doc_id, stored_hash[:12], new_hash[:12],
    )
    return ChangeStatus.CHANGED, stored_hash


# ════════════════════════════════════════════════
#  SUPERSESSION FLOW
# ════════════════════════════════════════════════


def run_supersession_flow(
    old_doc_id: str,
    new_doc_id: str,
    *,
    superseded_weight: float = 0.1,
) -> dict[str, Any]:
    """
    Mark old_doc_id as superseded by new_doc_id in the DB.

    Steps:
        1. Call db.client.supersede_document(old_doc_id, new_doc_id)
        2. Log outcome

    Returns the updated old document row dict, or raises if DB error.
    """
    from db.client import supersede_document

    log.info(
        "supersession: %s  →  %s  (weight=%s)",
        old_doc_id, new_doc_id, superseded_weight,
    )
    updated = supersede_document(
        old_doc_id,
        new_doc_id,
        superseded_weight=superseded_weight,
    )
    if updated is None:
        raise RuntimeError(
            f"Supersession failed: old_doc_id={old_doc_id!r} not found in DB."
        )
    log.info(
        "supersession OK: %s is now superseded  "
        "(document_status=%s, is_current=%s, retrieval_weight=%s)",
        old_doc_id,
        updated.get("document_status"),
        updated.get("is_current"),
        updated.get("retrieval_weight"),
    )
    return dict(updated)


# ════════════════════════════════════════════════
#  RE-CHUNK + RE-EMBED HELPER
# ════════════════════════════════════════════════


def _rechunk_and_embed(document_id: UUID, raw_path: Path, doc_id: str) -> int:
    """
    Delete existing chunks for *document_id* and re-ingest from *raw_path*.

    Returns the number of new chunks written.
    """
    from db.client import delete_chunks_for_document

    log.info("re-embed: deleting existing chunks for %s (%s)", doc_id, document_id)
    deleted = delete_chunks_for_document(document_id)
    log.info("re-embed: deleted %d chunks for %s", deleted, doc_id)

    # Lazy import to avoid circular imports at module load time
    from ingestion.chunker import chunk_document
    from ingestion.embedder import embed_and_store

    chunks = chunk_document(raw_path)
    if not chunks:
        log.warning("re-embed: no chunks produced for %s (empty or unreadable?)", doc_id)
        return 0

    written = embed_and_store(document_id, chunks)
    log.info("re-embed: wrote %d chunks for %s", written, doc_id)
    return written


# ════════════════════════════════════════════════
#  HIGH-LEVEL RESCRAPE ENTRY POINT
# ════════════════════════════════════════════════


def rescrape_document(
    doc_id: str,
    catalog_entry: dict[str, Any],
    raw_path: Path,
    new_content: bytes,
    *,
    force: bool = False,
    rechunk: bool = True,
) -> RescrapeResult:
    """
    Full rescrape flow for a single document.

    Args:
        doc_id:         The document's canonical identifier.
        catalog_entry:  The catalog dict for this doc (url, municipality, etc.).
        raw_path:       Path where the raw file is/will be stored.
        new_content:    Raw bytes just downloaded (or re-read from disk).
        force:          If True, treat every doc as CHANGED regardless of hash.
        rechunk:        If True (default), delete + re-embed chunks on change.

    Returns a RescrapeResult describing what happened.
    """
    result = RescrapeResult(doc_id=doc_id)
    new_hash = sha256_bytes(new_content)
    result.new_hash = new_hash

    # ── 1. Detect change ─────────────────────────────────────
    if force:
        status = ChangeStatus.CHANGED
        stored_hash = None
        result.messages.append("force=True — treating as CHANGED regardless of hash")
    else:
        status, stored_hash = check_document_changed(doc_id, new_hash)

    result.status = status
    result.old_hash = stored_hash

    if status == ChangeStatus.NO_CHANGE:
        result.messages.append(f"No change detected (hash={new_hash[:12]}…) — skipping")
        result.log_summary()
        return result

    # ── 2. Ingest new (or first) version ─────────────────────
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    from db.client import get_document_by_doc_id, insert_document

    if status == ChangeStatus.NEW_DOCUMENT:
        new_doc_id_str = doc_id
    else:
        # Append a datestamp to form the new doc_id versioned copy
        date_tag = datetime.now(timezone.utc).strftime("%Y%m%d")
        new_doc_id_str = f"{doc_id}-{date_tag}"

    result.new_doc_id = new_doc_id_str

    try:
        new_doc_row = insert_document(
            doc_id=new_doc_id_str,
            source_url=catalog_entry["url"],
            municipality=catalog_entry["municipality"],
            authority_level=catalog_entry["authority_level"],
            doc_type=catalog_entry["doc_type"],
            subject_tags=catalog_entry.get("subject_tags", []),
            document_status="active",
            is_current=True,
            retrieval_weight=1.0,
            checksum_sha256=new_hash,
            source_etag=catalog_entry.get("source_etag"),
            local_path=str(raw_path),
            source_tier=catalog_entry.get("source_tier", 1),
        )
        result.messages.append(
            f"Inserted new document row: {new_doc_id_str} (id={new_doc_row['id']})"
        )
    except Exception as exc:
        result.error = f"Failed to insert new document: {exc}"
        result.log_summary()
        return result

    new_document_uuid: UUID = new_doc_row["id"]

    # ── 3. Supersede the old version (if this is an update) ──
    if status == ChangeStatus.CHANGED:
        old_doc = get_document_by_doc_id(doc_id)
        if old_doc:
            try:
                run_supersession_flow(doc_id, new_doc_id_str)
                result.superseded = True
                result.messages.append(
                    f"Superseded old document: {doc_id} → {new_doc_id_str}"
                )
            except Exception as exc:
                # Non-fatal — new doc is already inserted, log and continue
                log.error(
                    "Supersession failed for %s: %s (continuing)", doc_id, exc
                )
                result.messages.append(f"WARNING: supersession failed: {exc}")
        else:
            result.messages.append(
                f"WARNING: old doc_id={doc_id!r} not found in DB — "
                "skipped supersession (possibly first run with renamed id)"
            )

    # ── 4. Re-chunk + re-embed ───────────────────────────────
    if rechunk:
        try:
            chunk_count = _rechunk_and_embed(new_document_uuid, raw_path, new_doc_id_str)
            result.messages.append(f"Re-embedded {chunk_count} chunks → {new_doc_id_str}")
        except Exception as exc:
            log.error("re-embed failed for %s: %s", new_doc_id_str, exc)
            result.messages.append(f"WARNING: re-embed failed: {exc}")
    else:
        result.messages.append("rechunk=False — skipping embedding step")

    result.log_summary()
    return result
