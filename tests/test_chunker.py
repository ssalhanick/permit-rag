"""
tests/test_chunker.py — Tests for ingestion/chunker.py
======================================================
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestDocxSupport:
    """Test DOCX extraction and discovery hooks."""

    def test_extract_text_routes_docx_to_handler(self, tmp_path: Path) -> None:
        """extract_text should route .docx files to DOCX extractor."""
        from ingestion.chunker import extract_text

        docx_path = tmp_path / "sample.docx"
        docx_path.write_bytes(b"placeholder")

        with patch("ingestion.chunker.extract_text_from_docx") as mock_docx:
            mock_docx.return_value = "docx content"
            extracted = extract_text(docx_path)

        assert extracted == "docx content"
        mock_docx.assert_called_once_with(docx_path)

    def test_find_raw_file_supports_docx(self, tmp_path: Path) -> None:
        """_find_raw_file should include .docx extension lookup."""
        from ingestion.chunker import _find_raw_file

        docx_path = tmp_path / "plano-udc.docx"
        docx_path.write_bytes(b"placeholder")

        found = _find_raw_file("plano-udc", tmp_path)
        assert found == docx_path

    def test_find_raw_file_prefers_docx_over_html(self, tmp_path: Path) -> None:
        """_find_raw_file should prefer docx before html for same doc_id."""
        from ingestion.chunker import _find_raw_file

        (tmp_path / "plano-code.html").write_text("html", encoding="utf-8")
        docx_path = tmp_path / "plano-code.docx"
        docx_path.write_bytes(b"placeholder")

        found = _find_raw_file("plano-code", tmp_path)
        assert found == docx_path


class TestNormalization:
    """Test procedural cleanup and balanced chunk filtering."""

    def test_clean_text_strips_procedural_line(self) -> None:
        """clean_text should remove procedural-only lines when enabled."""
        from ingestion.chunker import clean_text

        text = (
            "DULY PASSED AND APPROVED this the 1st day.\n"
            "A permit application shall include site plans.\n"
        )
        with patch.dict(
            "os.environ",
            {"CHUNK_NORMALIZATION_ENABLED": "true"},
            clear=False,
        ):
            cleaned = clean_text(text)
        assert "DULY PASSED AND APPROVED" not in cleaned
        assert "permit application shall include site plans" in cleaned.lower()

    def test_filter_chunks_drops_procedural_only_chunk(self) -> None:
        """filter_chunks should drop procedural-heavy chunk without requirements."""
        from ingestion.chunker import filter_chunks

        chunks = [
            {
                "chunk_index": 0,
                "content": "DULY PASSED AND APPROVED. ATTEST: APPROVED AS TO FORM. ORDINANCE NO. 2025-1-1.",
                "char_count": 90,
                "page_start": None,
                "page_end": None,
            },
            {
                "chunk_index": 1,
                "content": "A permit shall be required before construction begins.",
                "char_count": 60,
                "page_start": None,
                "page_end": None,
            },
        ]
        with patch.dict(
            "os.environ",
            {
                "CHUNK_PROCEDURAL_FILTER_ENABLED": "true",
                "CHUNK_PROCEDURAL_DROP_THRESHOLD": "3",
            },
            clear=False,
        ):
            kept, stats = filter_chunks(chunks)
        assert len(kept) == 1
        assert kept[0]["chunk_index"] == 1
        assert stats["dropped"] == 1

    def test_filter_chunks_keeps_mixed_requirement_text(self) -> None:
        """filter_chunks should keep mixed chunks that include requirement language."""
        from ingestion.chunker import filter_chunks

        chunks = [
            {
                "chunk_index": 2,
                "content": (
                    "ORDINANCE NO. 2025-1-1. DULY PASSED AND APPROVED. "
                    "A permit is required and inspections must be scheduled."
                ),
                "char_count": 140,
                "page_start": None,
                "page_end": None,
            }
        ]
        with patch.dict(
            "os.environ",
            {
                "CHUNK_PROCEDURAL_FILTER_ENABLED": "true",
                "CHUNK_PROCEDURAL_DROP_THRESHOLD": "2",
            },
            clear=False,
        ):
            kept, stats = filter_chunks(chunks)
        assert len(kept) == 1
        assert stats["dropped"] == 0
