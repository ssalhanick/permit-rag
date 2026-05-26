"""
tests/test_embedder.py — Tests for ingestion/embedder.py
=========================================================
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── Unit tests (no model loading) ────────────────────────────


class TestEmbedTexts:
    """Test embed_texts with mocked model."""

    @patch("ingestion.embedder.get_model")
    def test_returns_embeddings(self, mock_get_model):
        """embed_texts should return list of float lists."""
        from ingestion.embedder import embed_texts

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(2, 768)
        mock_get_model.return_value = mock_model

        embeddings = embed_texts(["hello", "world"])

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 768
        # Verify document prefix was applied
        call_args = mock_model.encode.call_args
        texts_sent = call_args[0][0]
        assert texts_sent[0].startswith("search_document: ")

    @patch("ingestion.embedder.get_model")
    def test_query_prefix(self, mock_get_model):
        """embed_texts with input_type='query' uses query prefix."""
        from ingestion.embedder import embed_texts

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(1, 768)
        mock_get_model.return_value = mock_model

        embed_texts(["test query"], input_type="query")

        call_args = mock_model.encode.call_args
        texts_sent = call_args[0][0]
        assert texts_sent[0].startswith("search_query: ")


class TestEmbedQuery:
    """Test embed_query convenience function."""

    @patch("ingestion.embedder.embed_texts")
    def test_returns_single_vector(self, mock_embed_texts):
        """embed_query should return a single embedding vector."""
        from ingestion.embedder import embed_query

        mock_embed_texts.return_value = [[0.5] * 768]
        result = embed_query("what permits do I need?")

        assert len(result) == 768
        mock_embed_texts.assert_called_once_with(
            ["what permits do I need?"],
            input_type="query",
            model_name=None,
        )


class TestEmbedDocumentChunks:
    """Test batch chunking logic."""

    @patch("ingestion.embedder.embed_texts")
    def test_extracts_content_from_chunks(self, mock_embed_texts):
        """Should extract 'content' key from chunk dicts."""
        from ingestion.embedder import embed_document_chunks

        chunks = [
            {"content": "chunk 0", "chunk_index": 0},
            {"content": "chunk 1", "chunk_index": 1},
        ]
        mock_embed_texts.return_value = [[0.1] * 768] * 2

        embeddings = embed_document_chunks(chunks)

        assert len(embeddings) == 2
        mock_embed_texts.assert_called_once_with(
            ["chunk 0", "chunk 1"],
            input_type="document",
            model_name=None,
        )


class TestModelSingleton:
    """Test model loading and unloading."""

    def test_unload_model(self):
        """unload_model should clear the cached model."""
        from ingestion.embedder import unload_model

        # Should not raise even if no model loaded
        unload_model()
