"""
ingestion/chunker.py — Text extraction + semantic chunking
==========================================================
Reads raw documents (HTML / PDF) from documents/raw/,
extracts clean text, and splits into overlapping chunks
sized for embedding.

Usage:
    from ingestion.chunker import chunk_document
    chunks = chunk_document("dallas-amlegal-code")
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from re import Pattern
from typing import Any

from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

log = logging.getLogger(__name__)

# ── Chunking defaults ────────────────────────────────────────
# Sized for Voyage-3 (8 K token context → ~3000 chars/chunk
# is safe with overlap for retrieval quality).
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200

# Where raw files live (relative to project root)
RAW_DIR = Path("documents/raw")

PROCEDURAL_PATTERNS: tuple[str, ...] = (
    r"\bduly passed and approved\b",
    r"\battest:",
    r"\bapproved as to form\b",
    r"\badopting and enacting supplement\b",
    r"\bordinance no\.",
)
REQUIREMENT_PATTERNS: tuple[str, ...] = (
    r"\bshall\b",
    r"\bmust\b",
    r"\brequired\b",
    r"\bpermit\b",
    r"\binspection\b",
    r"\bapplication\b",
    r"\bsetback\b",
    r"\bzoning district\b",
    r"\bsprinkler\b",
    r"\bfire code\b",
)
PROCEDURAL_REGEX = tuple(re.compile(p, re.IGNORECASE) for p in PROCEDURAL_PATTERNS)
REQUIREMENT_REGEX = tuple(re.compile(p, re.IGNORECASE) for p in REQUIREMENT_PATTERNS)


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """Parse a float environment variable with fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Parse an integer environment variable with fallback."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _count_pattern_hits(text: str, patterns: tuple[Pattern[str], ...]) -> int:
    """Count total regex hits from a pattern set."""
    return sum(len(pattern.findall(text)) for pattern in patterns)


def _strip_procedural_lines(text: str) -> str:
    """Remove obvious procedural boilerplate lines from source text."""
    kept_lines: list[str] = []
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            kept_lines.append(line)
            continue
        proc_hits = _count_pattern_hits(line_clean, PROCEDURAL_REGEX)
        req_hits = _count_pattern_hits(line_clean, REQUIREMENT_REGEX)
        if proc_hits > 0 and req_hits == 0:
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def filter_chunks(chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop procedural-heavy chunks that lack requirement language."""
    if not _env_bool("CHUNK_PROCEDURAL_FILTER_ENABLED", True):
        return chunks, {"before": len(chunks), "after": len(chunks), "dropped": 0, "drop_ratio": 0.0}
    drop_threshold = _env_int("CHUNK_PROCEDURAL_DROP_THRESHOLD", 3)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for chunk in chunks:
        content = str(chunk.get("content", ""))
        proc_hits = _count_pattern_hits(content, PROCEDURAL_REGEX)
        req_hits = _count_pattern_hits(content, REQUIREMENT_REGEX)
        if proc_hits >= drop_threshold and req_hits == 0:
            dropped += 1
            continue
        kept.append(chunk)
    before = len(chunks)
    after = len(kept)
    ratio = (dropped / before) if before else 0.0
    return kept, {"before": before, "after": after, "dropped": dropped, "drop_ratio": ratio}


# ════════════════════════════════════════════════
#  TEXT EXTRACTION
# ════════════════════════════════════════════════

def extract_text_from_pdf(path: Path) -> str:
    """
    Extract all text from a PDF, page by page.

    Returns a single string with page breaks marked by \\n\\n.
    Flags scanned (image-only) PDFs via empty-text detection.
    """
    reader = PdfReader(path)
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.strip())
    return "\n\n".join(pages)


def extract_text_from_html(path: Path) -> str:
    """
    Extract visible text from an HTML file.

    Strips scripts, styles, and nav elements to focus
    on the document body content.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    return text


def extract_text_from_docx(path: Path) -> str:
    """
    Extract paragraph text from a DOCX file.

    Returns a single string joined by newlines.
    Raises RuntimeError with install guidance if python-docx is unavailable.
    """
    try:
        from docx import Document  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "DOCX extraction requires python-docx. "
            "Install with: pip install python-docx"
        ) from exc

    document = Document(path)
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_text(path: Path) -> str:
    """
    Auto-detect file type and extract text.

    Returns the extracted text as a single string.
    Raises FileNotFoundError if the path doesn't exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Raw file not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix in (".html", ".htm"):
        return extract_text_from_html(path)
    elif suffix == ".docx":
        return extract_text_from_docx(path)
    else:
        # Fall back to plain text
        return path.read_text(encoding="utf-8", errors="replace")


# ════════════════════════════════════════════════
#  TEXT CLEANING
# ════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """
    Normalize whitespace and strip boilerplate noise.

    - Collapses runs of blank lines into at most two newlines
    - Strips leading/trailing whitespace per line
    - Removes common boilerplate phrases from code publishers
    """
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing spaces per line
    text = re.sub(r"[ \t]+\n", "\n", text)
    # Collapse horizontal whitespace runs
    text = re.sub(r"[ \t]{2,}", " ", text)
    if _env_bool("CHUNK_NORMALIZATION_ENABLED", True):
        text = _strip_procedural_lines(text)
    return text.strip()


# ════════════════════════════════════════════════
#  CHUNKING
# ════════════════════════════════════════════════

def split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """
    Split cleaned text into overlapping chunks.

    Returns a list of dicts, each with keys:
        chunk_index (int), content (str), char_count (int)

    Uses RecursiveCharacterTextSplitter for legal/code text,
    splitting on sections, paragraphs, sentences, then words.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=[
            "\n\n\n",   # section breaks
            "\n\n",      # paragraph breaks
            "\n",        # line breaks
            ". ",        # sentence ends
            "; ",        # clause breaks
            ", ",        # comma breaks
            " ",         # word breaks
        ],
        length_function=len,
        is_separator_regex=False,
    )

    docs = splitter.create_documents([text])

    chunks = []
    for i, doc in enumerate(docs):
        content = doc.page_content.strip()
        if not content:
            continue
        chunks.append({
            "chunk_index": i,
            "content": content,
            "char_count": len(content),
            "page_start": None,
            "page_end": None,
        })

    return chunks


# ════════════════════════════════════════════════
#  PUBLIC API
# ════════════════════════════════════════════════

def chunk_document(
    doc_id: str,
    raw_dir: Path | None = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> dict:
    """
    Full extraction + chunking pipeline for a single document.

    Looks up the raw file in documents/raw/ by doc_id (tries
    .pdf then .html extensions).

    Returns a dict with:
        doc_id       (str)
        raw_path     (Path)
        raw_chars    (int)   — chars in extracted text
        clean_chars  (int)   — chars after cleaning
        chunks       (list)  — list of chunk dicts
        num_chunks   (int)
        is_scanned   (bool)  — True if likely a scanned PDF
    """
    if raw_dir is None:
        raw_dir = RAW_DIR

    # Find the raw file
    path = _find_raw_file(doc_id, raw_dir)

    log.info("Extracting text: %s (%s)", doc_id, path.name)
    raw_text = extract_text(path)
    raw_chars = len(raw_text)

    # Detect scanned PDFs (very little text extracted)
    is_scanned = (
        path.suffix.lower() == ".pdf"
        and raw_chars < 200
    )
    if is_scanned:
        log.warning(
            "Scanned PDF detected: %s (%d chars extracted). "
            "Marking as needs_ocr.",
            doc_id, raw_chars,
        )

    clean = clean_text(raw_text)
    clean_chars = len(clean)

    chunks = split_text(clean, chunk_size, chunk_overlap)
    chunks, filter_stats = filter_chunks(chunks)
    warn_drop_ratio = _env_float("CHUNK_FILTER_WARN_DROP_RATIO", 0.50)
    if filter_stats["drop_ratio"] > warn_drop_ratio:
        log.warning(
            "High chunk drop ratio for %s: %.1f%% (%d/%d)",
            doc_id,
            filter_stats["drop_ratio"] * 100.0,
            filter_stats["dropped"],
            filter_stats["before"],
        )

    log.info(
        "Chunked %s: %d raw chars → %d clean chars → %d/%d chunks kept (dropped=%d)",
        doc_id,
        raw_chars,
        clean_chars,
        filter_stats["after"],
        filter_stats["before"],
        filter_stats["dropped"],
    )

    return {
        "doc_id": doc_id,
        "raw_path": path,
        "raw_chars": raw_chars,
        "clean_chars": clean_chars,
        "chunks": chunks,
        "num_chunks": len(chunks),
        "chunks_before_filter": filter_stats["before"],
        "chunks_dropped": filter_stats["dropped"],
        "chunk_drop_ratio": filter_stats["drop_ratio"],
        "is_scanned": is_scanned,
    }


def _find_raw_file(doc_id: str, raw_dir: Path) -> Path:
    """Locate the raw file for a doc_id, trying common extensions."""
    for ext in (".pdf", ".docx", ".txt", ".md", ".markdown", ".html", ".htm"):
        candidate = raw_dir / f"{doc_id}{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No raw file found for doc_id={doc_id!r} in {raw_dir}. "
        f"Tried extensions: .pdf, .docx, .txt, .md, .markdown, .html, .htm"
    )


# ════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract and chunk a single document"
    )
    parser.add_argument("doc_id", help="Document ID to process")
    parser.add_argument(
        "--chunk-size", type=int, default=CHUNK_SIZE,
        help=f"Chunk size in chars (default: {CHUNK_SIZE})",
    )
    parser.add_argument(
        "--chunk-overlap", type=int, default=CHUNK_OVERLAP,
        help=f"Chunk overlap in chars (default: {CHUNK_OVERLAP})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = chunk_document(
        args.doc_id,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    print(f"\n{'='*50}")
    print(f"  doc_id     : {result['doc_id']}")
    print(f"  raw_path   : {result['raw_path']}")
    print(f"  raw_chars  : {result['raw_chars']:,}")
    print(f"  clean_chars: {result['clean_chars']:,}")
    print(f"  num_chunks : {result['num_chunks']}")
    print(f"  is_scanned : {result['is_scanned']}")
    print(f"{'='*50}")

    if result["chunks"]:
        first = result["chunks"][0]
        print(f"\n  First chunk ({first['char_count']} chars):")
        print(f"  {first['content'][:200]}...")
