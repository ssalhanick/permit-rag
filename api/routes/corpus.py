"""
api/routes/corpus.py — Mobile corpus sync export (tier 1 subset).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.auth import get_current_user
from db import client as db_client

router = APIRouter(prefix="/corpus", tags=["corpus"])
CurrentUser = Annotated[dict, Depends(get_current_user)]


@router.get("/sync")
def corpus_sync(
    _current_user: CurrentUser,
    municipality: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    include_embeddings: bool = Query(default=False),
) -> dict:
    """
    Export municipality-scoped corpus chunks for on-device cache.

    Embeddings omitted by default to keep mobile payload small.
    """
    rows = db_client.list_corpus_sync_chunks(
        municipality=municipality.lower() if municipality else None,
        limit=limit,
        include_embeddings=include_embeddings,
    )
    chunks = []
    for row in rows:
        item = dict(row)
        if include_embeddings and item.get("embedding_text"):
            item["embedding"] = _parse_vector_text(item.pop("embedding_text"))
        else:
            item.pop("embedding_text", None)
        chunks.append(item)
    return {
        "municipality": municipality,
        "version": "registry-v1",
        "count": len(chunks),
        "chunks": chunks,
    }


def _parse_vector_text(text: str) -> list[float]:
    """Parse pgvector text representation into float list."""
    cleaned = text.strip().lstrip("[").rstrip("]")
    if not cleaned:
        return []
    return [float(part) for part in cleaned.split(",")]
