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

import os
import json
import hashlib
import logging
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── optional rich logging (falls back gracefully) ──
try:
    from rich.logging import RichHandler
    from rich.console import Console
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
    effective_date: Optional[str]      # ISO date string or None if unknown
    version: Optional[str]
    document_status: str               # active | superseded | draft | repealed
    is_current: bool
    supersedes_doc_id: Optional[str]
    review_due: str                    # ISO date — when to re-check this source

    # Ingestion tracking
    ingested_at: str
    checksum_sha256: str
    source_etag: Optional[str]         # HTTP ETag for change detection
    source_last_modified: Optional[str]
    file_size_bytes: int
    page_count: Optional[int]

    # RAG weighting hints
    retrieval_weight: float            # 1.0 default; lower for superseded docs
    notes: str                         # human-readable ingestion notes


# ════════════════════════════════════════════════
#  DOCUMENT CATALOG
#  Add / remove entries freely. Each dict becomes
#  one downloaded document with full metadata.
# ════════════════════════════════════════════════

DOCUMENT_CATALOG = [

    # ── DALLAS ──────────────────────────────────────────────────────────
    # City charter + 3 ordinance volumes exported from amlegal as PDF
    {
        "doc_id":          "city-of-dallas-charter",
        "url":             "https://codelibrary.amlegal.com/codes/dallas/latest/dallas_tx/0-0-0-1",
        "municipality":    "dallas",
        "authority_level": "municipal",
        "doc_type":        "administrative_rule",
        "subject_tags":    ["charter", "governance", "authority", "municipal"],
        "version":         None,
        "notes":           "Dallas City Charter — manually exported from amlegal PDF. "
                           "Defines city government structure and authority.",
        "review_days":     180,
    },
    {
        "doc_id":          "city-of-dallas-ordiance-v1",
        "url":             "https://codelibrary.amlegal.com/codes/dallas/latest/dallas_tx/0-0-0-1",
        "municipality":    "dallas",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning", "land-use", "setbacks", "easements",
                           "residential", "commercial", "ordinance"],
        "version":         None,
        "notes":           "Dallas Code of Ordinances Volume I — manually exported "
                           "from amlegal PDF. Review every 60 days.",
        "review_days":     60,
    },
    {
        "doc_id":          "city-of-dallas-ordiance-v2",
        "url":             "https://codelibrary.amlegal.com/codes/dallas/latest/dallas_tx/0-0-0-1",
        "municipality":    "dallas",
        "authority_level": "municipal",
        "doc_type":        "building_code",
        "subject_tags":    ["building-code", "construction", "permits",
                           "inspection", "ordinance"],
        "version":         None,
        "notes":           "Dallas Code of Ordinances Volume II — manually exported "
                           "from amlegal PDF. Review every 60 days.",
        "review_days":     60,
    },
    {
        "doc_id":          "city-of-dallas-ordiance-v3",
        "url":             "https://codelibrary.amlegal.com/codes/dallas/latest/dallas_tx/0-0-0-1",
        "municipality":    "dallas",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning", "land-use", "development",
                           "subdivision", "ordinance"],
        "version":         None,
        "notes":           "Dallas Code of Ordinances Volume III — manually exported "
                           "from amlegal PDF. Review every 60 days.",
        "review_days":     60,
    },
    {
        "doc_id":          "dallas-building-permit-checklist",
        "url":             "https://www.dallascityhall.com/departments/sustainabledevelopment/buildinginspection/DCH%20Documents/New%20One%20and%20Two%20Family%20Dwelling%20Checklist.pdf",
        "municipality":    "dallas",
        "authority_level": "municipal",
        "doc_type":        "permit_checklist",
        "subject_tags":    ["permit", "residential", "checklist", "inspection"],
        "version":         None,
        "notes":           "Dallas residential new construction permit checklist",
        "review_days":     60,
    },
    {
        "doc_id":          "dallas-fee-schedule",
        "url":             "https://www.dallascityhall.com/departments/sustainabledevelopment/buildinginspection/DCH%20Documents/Fee%20Schedule.pdf",
        "municipality":    "dallas",
        "authority_level": "municipal",
        "doc_type":        "other",
        "subject_tags":    ["fees", "permit", "inspection"],
        "version":         None,
        "notes":           "Dallas building inspection fee schedule — check every 30 days",
        "review_days":     30,
    },

    # ── PLANO ────────────────────────────────────────────────────────────
    {
        "doc_id":          "plano-municode-zoning",
        "url":             "https://library.municode.com/tx/plano/codes/code_of_ordinances",
        "municipality":    "plano",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning","land-use","setbacks","easements","residential","commercial"],
        "version":         None,
        "notes":           "Plano full municipal code via Municode",
        "review_days":     90,
    },
    {
        "doc_id":          "plano-building-permit-info",
        "url":             "https://www.plano.gov/2161/Building-Inspections",
        "municipality":    "plano",
        "authority_level": "municipal",
        "doc_type":        "permit_checklist",
        "subject_tags":    ["permit","checklist","inspection","residential","commercial"],
        "version":         None,
        "notes":           "Plano building inspections landing page — scrape for PDF links",
        "review_days":     60,
    },

    # ── FRISCO ───────────────────────────────────────────────────────────
    {
        "doc_id":          "frisco-municode-zoning",
        "url":             "https://library.municode.com/tx/frisco/codes/code_of_ordinances",
        "municipality":    "frisco",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning","land-use","setbacks","easements","residential","commercial"],
        "version":         None,
        "notes":           "Frisco full municipal code via Municode",
        "review_days":     90,
    },
    {
        "doc_id":          "frisco-unified-development-code",
        "url":             "https://www.friscotexas.gov/2785/Zoning-Ordinance",
        "municipality":    "frisco",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning","udc","land-use","development"],
        "version":         None,
        "notes":           "Frisco UDC landing page",
        "review_days":     90,
    },

    # ── MCKINNEY ─────────────────────────────────────────────────────────
    {
        "doc_id":          "mckinney-municode-zoning",
        "url":             "https://library.municode.com/tx/mckinney/codes/code_of_ordinances",
        "municipality":    "mckinney",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning","land-use","setbacks","easements","residential","commercial"],
        "version":         None,
        "notes":           "McKinney full municipal code via Municode",
        "review_days":     90,
    },

    # ── FORT WORTH ───────────────────────────────────────────────────────
    {
        "doc_id":          "fortworth-amlegal-code",
        "url":      "https://codelibrary.amlegal.com/codes/ftworth/latest/ftworth_tx/0-0-0-1",
        "municipality":    "fortworth",
        "authority_level": "municipal",
        "doc_type":        "zoning_ordinance",
        "subject_tags":    ["zoning","land-use","setbacks","easements","residential","commercial"],
        "version":         None,
        "notes":           "Fort Worth full code via American Legal Publishing.",
        "review_days":     60,
    },
    # UpCodes for Fort Worth building amendments
    {
        "doc_id":          "fortworth-upcodes-building",
        "url":             "https://up.codes/codes/fort-worth",
        "municipality":    "fortworth",
        "authority_level": "municipal",
        "doc_type":        "building_code",
        "subject_tags":    ["building-code", "amendments", "ordinance"],
        "version":         None,
        "notes":           "Fort Worth building code amendments with ordinance numbers "
                           "and effective dates. Good source for amendment tracking.",
        "review_days":     30,
    },

    # ── TEXAS STATE ──────────────────────────────────────────────────────
    {
        "doc_id":          "texas-accessibility-standards",
        "url":             "https://www.tdlr.texas.gov/ab/abtas.htm",
        "municipality":    "texas",
        "authority_level": "state",
        "doc_type":        "state_statute",
        "subject_tags":    ["accessibility","ADA","TAS","commercial","public-buildings"],
        "version":         "2012",
        "notes":           "Texas Accessibility Standards — TDLR. Apply statewide to all commercial projects.",
        "review_days":     180,
    },
    {
        "doc_id":          "texas-contractor-licensing-hvac",
        "url":             "https://www.tdlr.texas.gov/air/airforms.htm",
        "municipality":    "texas",
        "authority_level": "state",
        "doc_type":        "state_statute",
        "subject_tags":    ["licensing","HVAC","contractor","registration"],
        "version":         None,
        "notes":           "TDLR HVAC contractor licensing requirements",
        "review_days":     180,
    },
    {
        "doc_id":          "texas-contractor-licensing-electrical",
        "url":             "https://www.tdlr.texas.gov/electricians/elec.htm",
        "municipality":    "texas",
        "authority_level": "state",
        "doc_type":        "state_statute",
        "subject_tags":    ["licensing","electrical","contractor","registration"],
        "version":         None,
        "notes":           "TDLR electrical contractor licensing requirements",
        "review_days":     180,
    },
    {
        "doc_id":          "texas-contractor-licensing-plumbing",
        "url":             "https://www.tsbpe.texas.gov/licensing",
        "municipality":    "texas",
        "authority_level": "state",
        "doc_type":        "state_statute",
        "subject_tags":    ["licensing","plumbing","contractor","registration"],
        "version":         None,
        "notes":           "Texas State Board of Plumbing Examiners licensing",
        "review_days":     180,
    },

    # ── FEDERAL ──────────────────────────────────────────────────────────
    {
        "doc_id":          "osha-1926-construction",
        "url":             "https://www.osha.gov/laws-regs/regulations/standardnumber/1926",
        "municipality":    "federal",
        "authority_level": "federal",
        "doc_type":        "federal_regulation",
        "subject_tags":    ["OSHA","safety","fall-protection","scaffolding","electrical","excavation"],
        "version":         "1926",
        "notes":           "OSHA 29 CFR 1926 — Construction industry safety standards. Applies to all job sites.",
        "review_days":     365,
    },
    {
        "doc_id":          "ada-design-standards",
        "url":             "https://www.ada.gov/law-and-regs/design-standards/",
        "municipality":    "federal",
        "authority_level": "federal",
        "doc_type":        "federal_regulation",
        "subject_tags":    ["ADA","accessibility","design","commercial","public-accommodations"],
        "version":         "2010",
        "notes":           "ADA 2010 Design Standards — applies to all commercial construction.",
        "review_days":     365,
    },
    {
        "doc_id":          "epa-stormwater-construction",
        "url":             "https://www.epa.gov/npdes/stormwater-discharges-construction-activities",
        "municipality":    "federal",
        "authority_level": "federal",
        "doc_type":        "federal_regulation",
        "subject_tags":    ["EPA","stormwater","NPDES","erosion","grading","site-prep"],
        "version":         None,
        "notes":           "EPA NPDES stormwater requirements for construction sites over 1 acre.",
        "review_days":     365,
    },
]


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
    if "pdf" in content_type or url.lower().endswith(".pdf"):
        return f"{doc_id}.pdf"
    return f"{doc_id}.html"


def count_pdf_pages(path: Path) -> Optional[int]:
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
    today = datetime.utcnow().date().isoformat()
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
    now_iso = datetime.utcnow().isoformat() + "Z"

    results = {"success": [], "skipped": [], "failed": []}

    for entry in track(DOCUMENT_CATALOG, description="Harvesting documents..."):
        doc_id = entry["doc_id"]
        url = entry["url"]

        log.info(f"Processing: {doc_id}")

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

        # Save raw file
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
        review_due = (datetime.utcnow() + timedelta(days=review_days)).date().isoformat()

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
    log.info(f"Harvest complete")
    log.info(f"  Downloaded : {len(results['success'])}")
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
    registry[old_doc_id]["superseded_date"] = datetime.utcnow().date().isoformat()

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

    registry = load_registry(rp)
    today = datetime.utcnow().date().isoformat()

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
    print(f"  Total documents : {total}")
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