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

    def test_is_jurisdiction_or_overlay_doc_true_for_tier1_and_tier2(self) -> None:
        from ingestion.chunker import _is_jurisdiction_or_overlay_doc

        assert _is_jurisdiction_or_overlay_doc({"source_tier": 1, "overlay_id": None}) is True
        assert _is_jurisdiction_or_overlay_doc({"source_tier": 2, "overlay_id": None}) is True

    def test_is_jurisdiction_or_overlay_doc_true_for_overlay_regardless_of_tier(self) -> None:
        from ingestion.chunker import _is_jurisdiction_or_overlay_doc

        assert _is_jurisdiction_or_overlay_doc({"source_tier": 3, "overlay_id": "some-uuid"}) is True

    def test_is_jurisdiction_or_overlay_doc_false_for_plain_project_doc(self) -> None:
        """Type 2 (project drawings/plans) is explicitly out of scope for the prefix."""
        from ingestion.chunker import _is_jurisdiction_or_overlay_doc

        assert _is_jurisdiction_or_overlay_doc({"source_tier": 3, "overlay_id": None}) is False

    def test_is_jurisdiction_or_overlay_doc_false_for_missing_row(self) -> None:
        from ingestion.chunker import _is_jurisdiction_or_overlay_doc

        assert _is_jurisdiction_or_overlay_doc(None) is False

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
        """Context prefix off, but structure-aware splitting still needs doc_row
        at its own default -- so get_document_by_doc_id IS still called; the
        prefix itself just never gets applied."""
        from ingestion.chunker import chunk_document

        (tmp_path / "dallas-code.txt").write_text(
            "A permit shall be required before construction begins on any structure.",
            encoding="utf-8",
        )
        with patch(
            "db.client.get_document_by_doc_id",
            return_value={"source_tier": 1, "overlay_id": None, "municipality": "dallas",
                          "authority_level": "municipal", "doc_type": "building_code"},
        ), patch.dict("os.environ", {"CHUNK_CONTEXT_PREFIX_ENABLED": "false"}, clear=False):
            result = chunk_document("dallas-code", raw_dir=tmp_path)

        assert not result["chunks"][0]["content"].startswith("[")

    def test_chunk_document_skips_doc_row_fetch_when_both_flags_disabled(self, tmp_path: Path) -> None:
        from ingestion.chunker import chunk_document

        (tmp_path / "dallas-code.txt").write_text(
            "A permit shall be required before construction begins on any structure.",
            encoding="utf-8",
        )
        with patch("db.client.get_document_by_doc_id") as mock_get, \
             patch.dict(
                 "os.environ",
                 {
                     "CHUNK_CONTEXT_PREFIX_ENABLED": "false",
                     "CHUNK_STRUCTURE_AWARE_SPLITTING_ENABLED": "false",
                 },
                 clear=False,
             ):
            result = chunk_document("dallas-code", raw_dir=tmp_path)

        mock_get.assert_not_called()
        assert not result["chunks"][0]["content"].startswith("[")


class TestStructureAwareSplitting:
    """Chunking step 3 (document-upload plan): legal-section-aware splitting."""

    def test_section_header_regex_matches_section_symbol(self) -> None:
        from ingestion.chunker import SECTION_HEADER_REGEX

        assert SECTION_HEADER_REGEX.match("§ 51A-4.209 Setback requirements.")
        assert SECTION_HEADER_REGEX.match("§3.4.1 Fire sprinkler systems.")

    def test_section_header_regex_matches_sec_prefix(self) -> None:
        from ingestion.chunker import SECTION_HEADER_REGEX

        assert SECTION_HEADER_REGEX.match("Sec. 12.03.004 Building permits required.")
        assert SECTION_HEADER_REGEX.match("Section 3.4.1 Accessibility.")

    def test_section_header_regex_ignores_inline_reference(self) -> None:
        """A cross-reference mid-line ('see § 4.209 above') isn't a header --
        only a match anchored at the start of a line counts. This text has no
        newline, so '§ 4.209' never sits at a position '^' can match."""
        from ingestion.chunker import SECTION_HEADER_REGEX

        text = "As required by § 4.209 elsewhere in this code, permits apply."
        assert SECTION_HEADER_REGEX.search(text) is None

    def test_section_header_regex_requires_sub_numbering(self) -> None:
        """A bare '§ 5' with no dotted/hyphenated sub-number doesn't count --
        the plan specifies 'N.N.N-style numbering' specifically."""
        from ingestion.chunker import SECTION_HEADER_REGEX

        assert not SECTION_HEADER_REGEX.match("§ 5 General provisions.")

    def test_split_by_sections_returns_none_below_threshold(self) -> None:
        """Fewer than two section markers isn't enough signal -- fall back."""
        from ingestion.chunker import _split_by_sections

        assert _split_by_sections("Just plain prose, no sections at all.", 1500, 200) is None
        assert _split_by_sections("§ 3.1.1 Only one section marker here.", 1500, 200) is None

    def test_split_by_sections_splits_at_each_marker(self) -> None:
        from ingestion.chunker import _split_by_sections

        text = (
            "§ 3.1.1 Setbacks. Front yard setback shall be 25 feet minimum.\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet.\n"
            "§ 3.1.3 Lot coverage. Impervious coverage shall not exceed 45 percent."
        )
        segments = _split_by_sections(text, 1500, 200)

        assert len(segments) == 3
        assert segments[0].startswith("§ 3.1.1")
        assert segments[1].startswith("§ 3.1.2")
        assert segments[2].startswith("§ 3.1.3")

    def test_split_by_sections_preserves_leading_preamble(self) -> None:
        from ingestion.chunker import _split_by_sections

        text = (
            "ARTICLE 3. ZONING REGULATIONS. This article governs zoning citywide.\n"
            "§ 3.1.1 Setbacks. Front yard setback shall be 25 feet minimum.\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet."
        )
        segments = _split_by_sections(text, 1500, 200)

        assert len(segments) == 3
        assert segments[0].startswith("ARTICLE 3")
        assert segments[1].startswith("§ 3.1.1")

    def test_split_by_sections_sub_splits_oversized_section(self) -> None:
        from ingestion.chunker import _split_by_sections

        long_body = "This requirement applies broadly. " * 60  # well over 1500 chars
        text = (
            f"§ 3.1.1 Setbacks. {long_body}\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet."
        )
        segments = _split_by_sections(text, 500, 50)

        # The oversized § 3.1.1 section must have been broken into >1 piece,
        # each respecting the requested chunk_size.
        section_1_pieces = [s for s in segments if "This requirement applies" in s]
        assert len(section_1_pieces) > 1
        assert all(len(p) <= 500 + 50 for p in section_1_pieces)  # small slop for splitter boundaries

    def test_split_text_structure_aware_uses_section_boundaries(self) -> None:
        from ingestion.chunker import split_text

        text = (
            "§ 3.1.1 Setbacks. Front yard setback shall be 25 feet minimum.\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet.\n"
            "§ 3.1.3 Lot coverage. Impervious coverage shall not exceed 45 percent."
        )
        chunks = split_text(text, chunk_size=1500, chunk_overlap=200, structure_aware=True)

        assert len(chunks) == 3
        assert chunks[0]["content"].startswith("§ 3.1.1")

    def test_split_text_structure_aware_falls_back_without_sections(self) -> None:
        """No section markers -> identical output whether structure_aware is
        True or False, since _split_by_sections returns None either way."""
        from ingestion.chunker import split_text

        text = "Plain narrative text with no legal section numbering at all. " * 10
        aware = split_text(text, chunk_size=200, chunk_overlap=20, structure_aware=True)
        unaware = split_text(text, chunk_size=200, chunk_overlap=20, structure_aware=False)

        assert [c["content"] for c in aware] == [c["content"] for c in unaware]

    def test_chunk_document_uses_structure_aware_splitting_for_tier1(self, tmp_path: Path) -> None:
        from ingestion.chunker import chunk_document

        (tmp_path / "dallas-code.txt").write_text(
            "§ 3.1.1 Setbacks. Front yard setback shall be 25 feet minimum.\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet.\n"
            "§ 3.1.3 Lot coverage. Impervious coverage shall not exceed 45 percent.",
            encoding="utf-8",
        )
        with patch(
            "db.client.get_document_by_doc_id",
            return_value={"source_tier": 1, "overlay_id": None, "municipality": "dallas",
                          "authority_level": "municipal", "doc_type": "zoning_ordinance"},
        ), patch.dict(
            "os.environ",
            {"CHUNK_STRUCTURE_AWARE_SPLITTING_ENABLED": "true", "CHUNK_CONTEXT_PREFIX_ENABLED": "false"},
            clear=False,
        ):
            result = chunk_document("dallas-code", raw_dir=tmp_path)

        assert len(result["chunks"]) == 3
        assert result["chunks"][1]["content"].startswith("§ 3.1.2")

    def test_chunk_document_skips_structure_aware_for_project_doc(self, tmp_path: Path) -> None:
        """Type 2 project docs never use structure-aware splitting, even if
        their content happens to contain section-like numbering."""
        from ingestion.chunker import chunk_document

        (tmp_path / "project-doc-abc.txt").write_text(
            "§ 3.1.1 Setbacks. Front yard setback shall be 25 feet minimum.\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet.\n"
            "§ 3.1.3 Lot coverage. Impervious coverage shall not exceed 45 percent.",
            encoding="utf-8",
        )
        with patch(
            "db.client.get_document_by_doc_id",
            return_value={"source_tier": 3, "overlay_id": None, "municipality": "dallas",
                          "authority_level": "municipal", "doc_type": "other"},
        ), patch.dict(
            "os.environ",
            {"CHUNK_STRUCTURE_AWARE_SPLITTING_ENABLED": "true", "CHUNK_CONTEXT_PREFIX_ENABLED": "false"},
            clear=False,
        ):
            result = chunk_document("project-doc-abc", raw_dir=tmp_path)

        # Falls back to the generic splitter -- the whole short text becomes
        # one chunk rather than three section-aligned ones.
        assert len(result["chunks"]) == 1

    def test_chunk_document_respects_structure_aware_disabled_flag(self, tmp_path: Path) -> None:
        from ingestion.chunker import chunk_document

        (tmp_path / "dallas-code.txt").write_text(
            "§ 3.1.1 Setbacks. Front yard setback shall be 25 feet minimum.\n"
            "§ 3.1.2 Height limits. Maximum structure height shall be 35 feet.\n"
            "§ 3.1.3 Lot coverage. Impervious coverage shall not exceed 45 percent.",
            encoding="utf-8",
        )
        with patch(
            "db.client.get_document_by_doc_id",
            return_value={"source_tier": 1, "overlay_id": None, "municipality": "dallas",
                          "authority_level": "municipal", "doc_type": "zoning_ordinance"},
        ), patch.dict(
            "os.environ",
            {"CHUNK_STRUCTURE_AWARE_SPLITTING_ENABLED": "false", "CHUNK_CONTEXT_PREFIX_ENABLED": "false"},
            clear=False,
        ):
            result = chunk_document("dallas-code", raw_dir=tmp_path)

        # Generic splitter keeps this short text as one chunk instead of
        # aligning to the three § markers.
        assert len(result["chunks"]) == 1
