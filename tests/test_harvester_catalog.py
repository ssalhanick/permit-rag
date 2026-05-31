"""
tests/test_harvester_catalog.py — Catalog loader validation tests
=================================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.harvester import load_document_catalog


def _write_catalog(path: Path, entries: list[dict]) -> None:
    """Write helper catalog JSON for tests."""
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def test_load_document_catalog_valid(tmp_path: Path) -> None:
    """Loader should return entries for valid catalog JSON."""
    catalog_path = tmp_path / "catalog.json"
    entries = [
        {
            "doc_id": "test-doc",
            "url": "https://example.com/doc",
            "municipality": "dallas",
            "authority_level": "municipal",
            "doc_type": "zoning_ordinance",
        }
    ]
    _write_catalog(catalog_path, entries)
    loaded = load_document_catalog(catalog_path)
    assert loaded[0]["doc_id"] == "test-doc"


def test_load_document_catalog_rejects_missing_fields(tmp_path: Path) -> None:
    """Loader should raise when required fields are missing."""
    catalog_path = tmp_path / "catalog.json"
    entries = [{"doc_id": "bad-doc", "url": "https://example.com/doc"}]
    _write_catalog(catalog_path, entries)
    with pytest.raises(ValueError, match="missing required fields"):
        load_document_catalog(catalog_path)


def test_load_document_catalog_rejects_duplicates(tmp_path: Path) -> None:
    """Loader should raise when doc_id values are duplicated."""
    catalog_path = tmp_path / "catalog.json"
    entries = [
        {
            "doc_id": "dup-doc",
            "url": "https://example.com/doc1",
            "municipality": "dallas",
            "authority_level": "municipal",
            "doc_type": "zoning_ordinance",
        },
        {
            "doc_id": "dup-doc",
            "url": "https://example.com/doc2",
            "municipality": "plano",
            "authority_level": "municipal",
            "doc_type": "permit_checklist",
        },
    ]
    _write_catalog(catalog_path, entries)
    with pytest.raises(ValueError, match="Duplicate doc_id"):
        load_document_catalog(catalog_path)
