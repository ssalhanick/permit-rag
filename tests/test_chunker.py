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


class TestContextPrefix:
    """Chunking step 2 (document-upload plan): static, no-LLM context prefix."""

    def test_build_context_prefix_formats_full_metadata(self) -> None:
        from ingestion.chunker import _build_context_prefix

        prefix = _build_context_prefix({
            "municipality": "fort-worth",
            "authority_level": "municipal",
            "doc_type": "zoning_ordinance",
        })
        assert prefix == "[Fort Worth · municipal · zoning ordinance]\n"

    def test_build_context_prefix_empty_for_missing_row(self) -> None:
        from ingestion.chunker import _build_context_prefix

        assert _build_context_prefix(None) == ""
        assert _build_context_prefix({}) == ""

    def test_build_context_prefix_omits_missing_fields(self) -> None:
        from ingestion.chunker import _build_context_prefix

        prefix = _build_context_prefix({"municipality": "dallas", "authority_level": None, "doc_type": ""})
        assert prefix == "[Dallas]\n"

    def test_wants_context_prefix_true_for_tier1_and_tier2(self) -> None:
        from ingestion.chunker import _wants_context_prefix

        assert _wants_context_prefix({"source_tier": 1, "overlay_id": None}) is True
        assert _wants_context_prefix({"source_tier": 2, "overlay_id": None}) is True

    def test_wants_context_prefix_true_for_overlay_regardless_of_tier(self) -> None:
        from ingestion.chunker import _wants_context_prefix

        assert _wants_context_prefix({"source_tier": 3, "overlay_id": "some-uuid"}) is True

    def test_wants_context_prefix_false_for_plain_project_doc(self) -> None:
        """Type 2 (project drawings/plans) is explicitly out of scope for the prefix."""
        from ingestion.chunker import _wants_context_prefix

        assert _wants_context_prefix({"source_tier": 3, "overlay_id": None}) is False

    def test_wants_context_prefix_false_for_missing_row(self) -> None:
        from ingestion.chunker import _wants_context_prefix

        assert _wants_context_prefix(None) is False

    def test_chunk_document_prepends_prefix_for_tier1(self, tmp_path: Path) -> None:
        from ingestion.chunker import chunk_document

        (tmp_path / "dallas-code.txt").write_text(
            "A permit shall be required before construction begins on any structure.",
            encoding="utf-8",
        )
        with patch(
            "db.client.get_document_by_doc_id",
            return_value={"source_tier": 1, "overlay_id": None, "municipality": "dallas",
                          "authority_level": "municipal", "doc_type": "building_code"},
        ), patch.dict("os.environ", {"CHUNK_CONTEXT_PREFIX_ENABLED": "true"}, clear=False):
            result = chunk_document("dallas-code", raw_dir=tmp_path)

        assert result["chunks"], "expected at least one chunk"
        assert result["chunks"][0]["content"].startswith("[Dallas · municipal · building code]\n")

    def test_chunk_document_skips_prefix_for_project_doc(self, tmp_path: Path) -> None:
        from ingestion.chunker import chunk_document

        (tmp_path / "project-doc-abc.txt").write_text(
            "A permit shall be required before construction begins on any structure.",
            encoding="utf-8",
        )
        with patch(
            "db.client.get_document_by_doc_id",
            return_value={"source_tier": 3, "overlay_id": None, "municipality": "dallas",
                          "authority_level": "municipal", "doc_type": "other"},
        ), patch.dict("os.environ", {"CHUNK_CONTEXT_PREFIX_ENABLED": "true"}, clear=False):
            result = chunk_document("project-doc-abc", raw_dir=tmp_path)

        assert result["chunks"], "expected at least one chunk"
        assert not result["chunks"][0]["content"].startswith("[")

    def test_chunk_document_respects_disabled_flag(self, tmp_path: Path) -> None:
        from ingestion.chunker import chunk_document

        (tmp_path / "dallas-code.txt").write_text(
            "A permit shall be required before construction begins on any structure.",
            encoding="utf-8",
        )
        with patch("db.client.get_document_by_doc_id") as mock_get, \
             patch.dict("os.environ", {"CHUNK_CONTEXT_PREFIX_ENABLED": "false"}, clear=False):
            result = chunk_document("dallas-code", raw_dir=tmp_path)

        mock_get.assert_not_called()
        assert not result["chunks"][0]["content"].startswith("[")
