"""
DFW Construction Document Harvester
====================================
Downloads, names, and tags municipal permit/zoning documents
for Dallas, Plano, Frisco, McKinney + state/federal sources.

Usage:
    pip install requests beautifulsoup4 pypdf2 rich schedule
    python dfw_doc_harvester.py

Output:
    ./documents/
        raw/          <- downloaded PDFs + HTML
        metadata/     <- JSON sidecar per document
        registry.json <- master document registry
        harvest.log   <- full run log
"""

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

# ── optional rich logging (falls back gracefully) ──
try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.progress import track
    console = Console()
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler("harvest.log"),
            logging.StreamHandler()
        ]
    )
    def track(iterable, description=""):
        return iterable

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════
#  DATA MODEL
# ════════════════════════════════════════════════

@dataclass
class DocumentMetadata:
    """
    Every field here maps directly to your pgvector metadata schema.
    Attach this to every chunk when you embed later.
    """
    # Identity
    doc_id: str                        # e.g. "dallas-zoning-ord-2024-03"
    source_url: str
    local_path: str                    # relative path under documents/raw/
    filename: str

    # Classification
    municipality: str                  # dallas | plano | frisco | mckinney | texas | federal
    authority_level: str               # municipal | state | federal
    doc_type: str                      # zoning_ordinance | building_code | fee_schedule |
                                       # permit_checklist | state_statute | federal_regulation
    subject_tags: list                 # ["easements","setbacks","residential"]

    # Temporal governance
    effective_date: str | None      # ISO date string or None if unknown
    version: str | None
    document_status: str               # active | superseded | draft | repealed
    is_current: bool
    supersedes_doc_id: str | None
    review_due: str                    # ISO date — when to re-check this source

    # Ingestion tracking
    ingested_at: str
    checksum_sha256: str
    source_etag: str | None         # HTTP ETag for change detection
    source_last_modified: str | None
    file_size_bytes: int
    page_count: int | None

    # RAG weighting hints
    retrieval_weight: float            # 1.0 default; lower for superseded docs
    notes: str                         # human-readable ingestion notes


# ════════════════════════════════════════════════
#  DOCUMENT CATALOG (JSON-backed)
# ════════════════════════════════════════════════

CATALOG_PATH = Path(__file__).resolve().parents[1] / "documents" / "catalog.json"
REQUIRED_CATALOG_FIELDS: tuple[str, ...] = (
    "doc_id",
    "url",
    "municipality",
    "authority_level",
    "doc_type",
)


def _validate_catalog_entry(entry: dict[str, Any], index: int) -> None:
    """Validate required keys and minimal shape for catalog entries."""
    missing = [k for k in REQUIRED_CATALOG_FIELDS if k not in entry]
    if missing:
        raise ValueError(
            f"Catalog entry at index {index} missing required fields: {missing}"
        )
    if not str(entry["doc_id"]).strip():
        raise ValueError(f"Catalog entry at index {index} has empty doc_id")
    if not str(entry["url"]).strip():
        raise ValueError(
            f"Catalog entry '{entry.get('doc_id', index)}' has empty url"
        )


def load_document_catalog(catalog_path: Path | None = None) -> list[dict[str, Any]]:
    """Load and validate document catalog entries from JSON."""
    path = catalog_path or CATALOG_PATH
    if not path.exists():
        raise RuntimeError(
            f"Document catalog not found at {path}. "
            "Create documents/catalog.json before running harvester."
        )
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in catalog file: {path}") from exc
    if not isinstance(loaded, list):
        raise RuntimeError(f"Catalog file must contain a JSON array: {path}")
    seen_doc_ids: set[str] = set()
    for idx, item in enumerate(loaded):
        if not isinstance(item, dict):
            raise ValueError(f"Catalog entry at index {idx} must be an object")
        _validate_catalog_entry(item, idx)
        doc_id = str(item["doc_id"])
        if doc_id in seen_doc_ids:
            raise ValueError(f"Duplicate doc_id in catalog: {doc_id}")
        seen_doc_ids.add(doc_id)
    return loaded


# ════════════════════════════════════════════════
#  REVIEW SCHEDULE LOOKUP
# ════════════════════════════════════════════════

REVIEW_DAYS_BY_TYPE = {
    "fee_schedule":        30,
    "permit_checklist":    60,
    "zoning_ordinance":    90,
    "building_code":       180,
    "state_statute":       180,
    "federal_regulation":  365,
}


# ════════════════════════════════════════════════
#  DOWNLOADER
# ════════════════════════════════════════════════

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DFW-RAG-Harvester/1.0; "
        "+https://github.com/yourusername/dfw-rag)"
    )
}


def _find_existing_raw_file(doc_id: str, raw_dir: Path) -> Path | None:
    """Return existing raw file path for doc_id, if present."""
    for ext in (".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"):
        candidate = raw_dir / f"{doc_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def fetch_document(url: str, timeout: int = 30):
    """
    Fetch a URL. Returns (content_bytes, etag, last_modified, content_type).
    Raises on non-200.
    """
    resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    etag = resp.headers.get("ETag")
    last_modified = resp.headers.get("Last-Modified")
    content_type = resp.headers.get("Content-Type", "")
    return resp.content, etag, last_modified, content_type


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(doc_id: str, content_type: str, url: str) -> str:
    """Derive a clean local filename from doc_id + content type."""
    lowered_type = (content_type or "").lower()
    lowered_url = url.lower()
    if "pdf" in lowered_type or lowered_url.endswith(".pdf"):
        return f"{doc_id}.pdf"
    if (
        "wordprocessingml.document" in lowered_type
        or lowered_url.endswith(".docx")
    ):
        return f"{doc_id}.docx"
    if lowered_type.startswith("text/markdown") or lowered_url.endswith(
        (".md", ".markdown")
    ):
        return f"{doc_id}.md"
    if lowered_type.startswith("text/plain") or lowered_url.endswith(".txt"):
        return f"{doc_id}.txt"
    return f"{doc_id}.html"


def count_pdf_pages(path: Path) -> int | None:
    """Count pages in a PDF without heavy dependencies."""
    try:
        content = path.read_bytes()
        # Fast heuristic: count /Page dictionary entries
        count = content.count(b"/Type /Page") or content.count(b"/Type/Page")
        return count if count > 0 else None
    except Exception:
        return None


# ════════════════════════════════════════════════
#  SUBJECT TAG INFERENCE
# ════════════════════════════════════════════════

KEYWORD_TAG_MAP = {
    "easement":        "easements",
    "setback":         "setbacks",
    "residential":     "residential",
    "commercial":      "commercial",
    "fee":             "fees",
    "permit":          "permit",
    "inspection":      "inspection",
    "checklist":       "checklist",
    "zoning":          "zoning",
    "electrical":      "electrical",
    "plumbing":        "plumbing",
    "hvac":            "hvac",
    "mechanical":      "mechanical",
    "fire":            "fire-safety",
    "accessibility":   "accessibility",
    "ada":             "ADA",
    "osha":            "OSHA",
    "stormwater":      "stormwater",
    "grading":         "grading",
    "foundation":      "foundation",
    "framing":         "framing",
    "roofing":         "roofing",
    "land use":        "land-use",
    "land-use":        "land-use",
}

def infer_tags_from_content(text_snippet: str, base_tags: list) -> list:
    """Add extra tags inferred from first 2000 chars of document content."""
    snippet_lower = text_snippet[:2000].lower()
    extra = set()
    for keyword, tag in KEYWORD_TAG_MAP.items():
        if keyword in snippet_lower:
            extra.add(tag)
    return list(set(base_tags) | extra)


# ════════════════════════════════════════════════
#  REGISTRY
# ════════════════════════════════════════════════

def load_registry(registry_path: Path) -> dict:
    if registry_path.exists():
        content = registry_path.read_text().strip()
        if content:
            return json.loads(content)
    return {}

def save_registry(registry: dict, registry_path: Path):
    registry_path.write_text(json.dumps(registry, indent=2))


# ════════════════════════════════════════════════
#  CHANGE DETECTION
# ════════════════════════════════════════════════

def check_for_updates(registry: dict) -> list:
    """
    HEAD-check all active documents. Return list of doc_ids where
    the source appears to have changed since last harvest.
    """
    changed = []
    for doc_id, meta in registry.items():
        if meta.get("document_status") != "active":
            continue
        url = meta["source_url"]
        stored_etag = meta.get("source_etag")
        stored_lm = meta.get("source_last_modified")
        try:
            resp = requests.head(url, headers=HEADERS, timeout=15, allow_redirects=True)
            current_etag = resp.headers.get("ETag")
            current_lm = resp.headers.get("Last-Modified")
            if (stored_etag and current_etag and stored_etag != current_etag):
                log.warning(f"[CHANGED] {doc_id} — ETag mismatch")
                changed.append(doc_id)
            elif (stored_lm and current_lm and stored_lm != current_lm):
                log.warning(f"[CHANGED] {doc_id} — Last-Modified changed")
                changed.append(doc_id)
            time.sleep(0.5)
        except Exception as e:
            log.error(f"[HEAD FAIL] {doc_id}: {e}")
    return changed


def find_overdue_reviews(registry: dict) -> list:
    """Return list of doc_ids past their review_due date."""
    today = datetime.now(UTC).date().isoformat()
    overdue = []
    for doc_id, meta in registry.items():
        review_due = meta.get("review_due", "")
        if review_due and review_due < today:
            overdue.append(doc_id)
    return overdue


# ════════════════════════════════════════════════
#  MAIN HARVEST
# ════════════════════════════════════════════════

def harvest(output_dir: str = "documents", force: bool = False):
    """
    Download all catalog documents, write metadata sidecars,
    and update the master registry.
    """
    base = Path(output_dir)
    raw_dir = base / "raw"
    meta_dir = base / "metadata"
    raw_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    registry_path = base / "registry.json"

    registry = load_registry(registry_path)
    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    catalog = load_document_catalog()
    results = {
        "success": [],
        "skipped": [],
        "failed": [],
        "used_local_raw": 0,
        "downloaded_from_url": 0,
    }

    for entry in track(catalog, description="Harvesting documents..."):
        doc_id = entry["doc_id"]
        url = entry["url"]

        log.info(f"Processing: {doc_id}")
        existing_raw = _find_existing_raw_file(doc_id, raw_dir)
        used_local_raw = existing_raw is not None and not force

        if used_local_raw:
            results["used_local_raw"] += 1
            log.info("  Using existing local raw file: %s", existing_raw.name)
            content = existing_raw.read_bytes()
            previous = registry.get(doc_id, {})
            etag = previous.get("source_etag")
            last_modified = previous.get("source_last_modified")
            suffix = existing_raw.suffix.lower()
            if suffix == ".pdf":
                content_type = "application/pdf"
            elif suffix == ".docx":
                content_type = (
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                )
            elif suffix in {".md", ".markdown"}:
                content_type = "text/markdown"
            elif suffix == ".txt":
                content_type = "text/plain"
            else:
                content_type = "text/html"
        else:
            results["downloaded_from_url"] += 1
            try:
                content, etag, last_modified, content_type = fetch_document(url)
            except Exception as e:
                log.error(f"  FAILED to fetch {url}: {e}")
                results["failed"].append({"doc_id": doc_id, "error": str(e)})
                continue

        checksum = sha256_of(content)

        # Skip if unchanged (same checksum already in registry)
        if not force and doc_id in registry:
            if registry[doc_id].get("checksum_sha256") == checksum:
                log.info(f"  SKIPPED (unchanged): {doc_id}")
                results["skipped"].append(doc_id)
                continue

        # Save raw file (or reuse existing local one)
        if used_local_raw:
            raw_path = existing_raw
            filename = raw_path.name
        else:
            filename = safe_filename(doc_id, content_type, url)
            raw_path = raw_dir / filename
            raw_path.write_bytes(content)

        # Page count for PDFs
        page_count = None
        if filename.endswith(".pdf"):
            page_count = count_pdf_pages(raw_path)

        # Infer extra tags from content snippet
        text_snippet = content[:2000].decode("utf-8", errors="ignore")
        subject_tags = infer_tags_from_content(text_snippet, entry.get("subject_tags", []))

        # Calculate review due date
        review_days = entry.get(
            "review_days",
            REVIEW_DAYS_BY_TYPE.get(entry["doc_type"], 90)
        )
        review_due = (
            datetime.now(UTC) + timedelta(days=review_days)
        ).date().isoformat()

        # Build metadata object
        meta = DocumentMetadata(
            doc_id=doc_id,
            source_url=url,
            local_path=str(raw_path.relative_to(base)),
            filename=filename,
            municipality=entry["municipality"],
            authority_level=entry["authority_level"],
            doc_type=entry["doc_type"],
            subject_tags=subject_tags,
            effective_date=entry.get("effective_date"),
            version=entry.get("version"),
            document_status="active",
            is_current=True,
            supersedes_doc_id=entry.get("supersedes_doc_id"),
            review_due=review_due,
            ingested_at=now_iso,
            checksum_sha256=checksum,
            source_etag=etag,
            source_last_modified=last_modified,
            file_size_bytes=len(content),
            page_count=page_count,
            retrieval_weight=1.0,
            notes=entry.get("notes", ""),
        )

        # Write JSON sidecar
        sidecar_path = meta_dir / f"{doc_id}.json"
        sidecar_path.write_text(json.dumps(asdict(meta), indent=2))

        # Update registry
        registry[doc_id] = asdict(meta)

        log.info(
            f"  OK: {filename} "
            f"({len(content)/1024:.1f} KB"
            + (f", {page_count}p" if page_count else "")
            + ")"
        )
        results["success"].append(doc_id)
        time.sleep(1.0)  # be polite to servers

    save_registry(registry, registry_path)

    # ── Summary ──
    log.info("\n" + "="*50)
    log.info("Harvest complete")
    log.info(f"  Downloaded : {len(results['success'])}")
    log.info(f"  Used local raw     : {results['used_local_raw']}")
    log.info(f"  Downloaded from URL: {results['downloaded_from_url']}")
    log.info(f"  Skipped    : {len(results['skipped'])} (unchanged)")
    log.info(f"  Failed     : {len(results['failed'])}")

    # Check for overdue reviews
    overdue = find_overdue_reviews(registry)
    if overdue:
        log.warning(f"\n  OVERDUE REVIEWS ({len(overdue)}):")
        for doc_id in overdue:
            log.warning(f"    - {doc_id}")

    log.info(f"\n  Registry saved: {registry_path}")
    log.info(f"  Raw files:      {raw_dir}")
    log.info(f"  Metadata:       {meta_dir}")
    return results


# ════════════════════════════════════════════════
#  CHANGE MONITOR (run this on a schedule)
# ════════════════════════════════════════════════

def monitor():
    """
    HEAD-check all active documents for changes.
    Run this weekly (cron or EventBridge Lambda).
    Prints a report of anything that changed.
    """
    registry_path = Path("documents/registry.json")
    if not registry_path.exists():
        log.error("No registry found. Run harvest() first.")
        return

    registry = load_registry(registry_path)
    log.info(f"Checking {len(registry)} documents for changes...")

    changed = check_for_updates(registry)
    overdue = find_overdue_reviews(registry)

    log.info("\n── Monitor Report ──────────────────────────")
    if changed:
        log.warning(f"Source changed ({len(changed)}) — re-harvest these:")
        for d in changed:
            log.warning(f"  {d}")
    else:
        log.info("No source changes detected.")

    if overdue:
        log.warning(f"\nOverdue for review ({len(overdue)}):")
        for d in overdue:
            due = registry[d].get("review_due", "unknown")
            log.warning(f"  {d}  (due: {due})")
    else:
        log.info("No overdue reviews.")


# ════════════════════════════════════════════════
#  SUPERSESSION HELPER
# ════════════════════════════════════════════════

def mark_superseded(old_doc_id: str, new_doc_id: str, registry_path: str = "documents/registry.json"):
    """
    When a new version of a document replaces an old one,
    call this to update the registry correctly.

    Example:
        mark_superseded("dallas-zoning-ord-2022-11", "dallas-zoning-ord-2024-03")
    """
    rp = Path(registry_path)
    registry = load_registry(rp)

    if old_doc_id not in registry:
        log.error(f"doc_id not found in registry: {old_doc_id}")
        return

    registry[old_doc_id]["document_status"] = "superseded"
    registry[old_doc_id]["is_current"] = False
    registry[old_doc_id]["retrieval_weight"] = 0.1
    registry[old_doc_id]["superseded_by"] = new_doc_id
    registry[old_doc_id]["superseded_date"] = datetime.now(
        UTC
    ).date().isoformat()

    if new_doc_id in registry:
        registry[new_doc_id]["supersedes_doc_id"] = old_doc_id

    save_registry(registry, rp)

    # Update sidecar
    meta_path = Path("documents/metadata") / f"{old_doc_id}.json"
    if meta_path.exists():
        meta_path.write_text(json.dumps(registry[old_doc_id], indent=2))

    log.info(f"Marked {old_doc_id} as superseded by {new_doc_id}")


# ════════════════════════════════════════════════
#  REGISTRY REPORT
# ════════════════════════════════════════════════

def print_registry_report():
    """Print a human-readable governance summary of your document library."""
    rp = Path("documents/registry.json")
    if not rp.exists():
        log.error("No registry found.")
        return

    catalog = load_document_catalog()
    registry = load_registry(rp)
    today = datetime.now(UTC).date().isoformat()

    catalog_doc_ids = {str(entry["doc_id"]) for entry in catalog}
    registry_doc_ids = set(registry.keys())
    missing_from_registry = sorted(catalog_doc_ids - registry_doc_ids)

    total_catalog = len(catalog_doc_ids)
    total = len(registry)
    active = sum(1 for m in registry.values() if m["document_status"] == "active")
    superseded = sum(1 for m in registry.values() if m["document_status"] == "superseded")
    overdue = [d for d, m in registry.items() if m.get("review_due", "") < today]

    # Group by municipality
    by_muni = {}
    for doc_id, meta in registry.items():
        muni = meta["municipality"]
        by_muni.setdefault(muni, []).append(doc_id)

    print("\n" + "="*60)
    print("  DFW RAG Document Registry Report")
    print("="*60)
    print(f"  Catalog documents  : {total_catalog}")
    print(f"  Registry documents : {total}")
    print(f"  Missing from registry: {len(missing_from_registry)}")
    print(f"  Active          : {active}")
    print(f"  Superseded      : {superseded}")
    print(f"  Overdue review  : {len(overdue)}")
    print()
    print("  By municipality:")
    for muni, docs in sorted(by_muni.items()):
        print(f"    {muni:<12} {len(docs)} documents")
    if overdue:
        print()
        print("  OVERDUE:")
        for d in overdue:
            print(f"    {d}  (due: {registry[d].get('review_due')})")
    if missing_from_registry:
        print()
        print("  MISSING FROM REGISTRY:")
        for doc_id in missing_from_registry:
            print(f"    {doc_id}")
    print("="*60 + "\n")


# ════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DFW Construction Document Harvester")
    parser.add_argument(
        "command",
        choices=["harvest", "monitor", "report"],
        default="harvest",
        nargs="?",
        help="harvest=download all docs | monitor=check for changes | report=show registry"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if checksum unchanged"
    )
    parser.add_argument(
        "--output",
        default="documents",
        help="Output directory (default: ./documents)"
    )
    args = parser.parse_args()

    if args.command == "harvest":
        harvest(output_dir=args.output, force=args.force)
    elif args.command == "monitor":
        monitor()
    elif args.command == "report":
        print_registry_report()