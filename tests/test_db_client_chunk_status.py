"""Tests that chunk retrieval SQL uses chunks.status, not chunk_status column."""

from __future__ import annotations

from pathlib import Path


CLIENT_PY = Path(__file__).resolve().parent.parent / "db" / "client.py"
SOURCE = CLIENT_PY.read_text(encoding="utf-8")


def _extract_sql(func_name: str) -> str:
    """Return the triple-quoted SQL block for a db.client function."""
    marker = f"def {func_name}("
    start = SOURCE.index(marker)
    sql_start = SOURCE.index('sql = """', start) + len('sql = """')
    sql_end = SOURCE.index('"""', sql_start)
    return SOURCE[sql_start:sql_end]


def test_match_project_chunks_uses_status_column() -> None:
    """Project-scoped retrieval must filter on chunks.status."""
    sql = _extract_sql("match_project_chunks")
    assert "c.status" in sql
    assert "c.chunk_status" not in sql
    assert "AS chunk_status" in sql


def test_get_chunks_by_ids_uses_status_column() -> None:
    """Chunk-ID hydration must filter on chunks.status."""
    sql = _extract_sql("get_chunks_by_ids")
    assert "c.status" in sql
    assert "c.chunk_status" not in sql
    assert "AS chunk_status" in sql


def test_list_corpus_sync_chunks_uses_status_column() -> None:
    """Corpus sync export must filter on chunks.status."""
    marker = "def list_corpus_sync_chunks("
    start = SOURCE.index(marker)
    next_def = SOURCE.index("\ndef ", start + 1)
    body = SOURCE[start:next_def]
    assert "c.status = 'active'" in body
    assert "c.chunk_status" not in body
