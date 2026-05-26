"""
ingestion/embedder.py — nomic-embed-text-v1.5 embedding pipeline
=================================================================
Embeds chunked document text locally via sentence-transformers and
stores the resulting vectors in the chunks table (pgvector column).

All database writes go through db/client.py (see AGENTS.md).

Model: nomic-ai/nomic-embed-text-v1.5
  - 768 dimensions (default)
  - 8192 token context window
  - Prefixes: "search_document: " for docs, "search_query: " for queries
  - Matryoshka: supports 768, 512, 256, 128 dims
  - Free local inference — no API key required

Usage:
    from ingestion.embedder import embed_document, embed_all_documents
    from ingestion.embedder import embed_query
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
from uuid import UUID

log = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────
DEFAULT_MODEL = "nomic-ai/nomic-embed-text-v1.5"
EMBEDDING_DIM = 768

# Process chunks in batches to manage memory on CPU
BATCH_SIZE = 64

# Prefixes required by nomic-embed-text
_DOC_PREFIX = "search_document: "
_QUERY_PREFIX = "search_query: "


# ════════════════════════════════════════════════
#  MODEL (singleton — loaded once, reused)
# ════════════════════════════════════════════════

_model = None


def get_model(model_name: Optional[str] = None):
    """
    Load (or return cached) SentenceTransformer model.

    The model is loaded once and cached for the process lifetime.
    Uses GPU if available, otherwise CPU.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        name = model_name or os.environ.get(
            "EMBEDDING_MODEL", DEFAULT_MODEL
        )
        log.info("Loading embedding model: %s", name)
        _model = SentenceTransformer(
            name, trust_remote_code=True
        )
        device = _model.device
        log.info("Model loaded on device: %s", device)
    return _model


def unload_model() -> None:
    """Free the model from memory (useful after batch jobs)."""
    global _model
    if _model is not None:
        del _model
        _model = None
        log.info("Embedding model unloaded")


# ════════════════════════════════════════════════
#  CORE: Embed a batch of texts
# ════════════════════════════════════════════════

def embed_texts(
    texts: list[str],
    *,
    input_type: str = "document",
    model_name: Optional[str] = None,
) -> list[list[float]]:
    """
    Embed a list of texts using nomic-embed-text-v1.5.

    Args:
        texts: List of text strings to embed.
        input_type: 'document' for ingestion, 'query' for search.
        model_name: Optional model override.

    Returns:
        List of embedding vectors (768-dim float lists).
    """
    model = get_model(model_name)

    # Apply the correct prefix
    prefix = _QUERY_PREFIX if input_type == "query" else _DOC_PREFIX
    prefixed = [prefix + t for t in texts]

    embeddings = model.encode(
        prefixed,
        batch_size=BATCH_SIZE,
        show_progress_bar=len(texts) > BATCH_SIZE,
        normalize_embeddings=True,
    )

    # Convert numpy arrays to plain lists for JSON/pgvector compat
    return [emb.tolist() for emb in embeddings]


def embed_query(
    query: str,
    *,
    model_name: Optional[str] = None,
) -> list[float]:
    """
    Embed a single search query for retrieval.

    Returns a 768-dim float vector.
    """
    results = embed_texts(
        [query], input_type="query", model_name=model_name
    )
    return results[0]


# ════════════════════════════════════════════════
#  BATCH: Embed chunks for a document
# ════════════════════════════════════════════════

def embed_document_chunks(
    chunks: list[dict[str, Any]],
    *,
    model_name: Optional[str] = None,
) -> list[list[float]]:
    """
    Embed all chunks for a single document.

    Args:
        chunks: List of chunk dicts with 'content' key.
        model_name: Optional model override.

    Returns:
        List of embedding vectors (one per chunk).
    """
    texts = [c["content"] for c in chunks]

    log.info("Embedding %d chunks...", len(texts))
    embeddings = embed_texts(
        texts, input_type="document", model_name=model_name
    )
    log.info("Embedded %d chunks (%d-dim)", len(embeddings), len(embeddings[0]))

    return embeddings


# ════════════════════════════════════════════════
#  STORAGE: Write embeddings to pgvector
# ════════════════════════════════════════════════

def store_embeddings(
    document_id: UUID,
    chunk_indices: list[int],
    embeddings: list[list[float]],
) -> int:
    """
    Write embedding vectors to the chunks table.

    Updates existing chunk rows by (document_id, chunk_index).
    Returns the number of rows updated.

    All SQL goes through db/client.py (AGENTS.md rule).
    """
    from db.client import get_conn

    sql = """
        UPDATE chunks
        SET embedding = %(embedding)s::vector
        WHERE document_id = %(document_id)s
          AND chunk_index = %(chunk_index)s;
    """
    updated = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for idx, emb in zip(chunk_indices, embeddings):
                cur.execute(sql, {
                    "document_id": document_id,
                    "chunk_index": idx,
                    "embedding": str(emb),
                })
                updated += cur.rowcount
        conn.commit()

    log.info(
        "Stored %d embeddings for document %s",
        updated, document_id,
    )
    return updated


# ════════════════════════════════════════════════
#  PIPELINE: Full embed + store for one document
# ════════════════════════════════════════════════

def embed_document(
    doc_id: str,
    *,
    model_name: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Full embedding pipeline for a single document.

    1. Loads chunks from DB (must already be chunked + inserted)
    2. Skips chunks that already have embeddings
    3. Runs local inference via sentence-transformers
    4. Stores vectors back to pgvector
    5. Runs embedding verification

    Args:
        doc_id: Human-readable document ID.
        model_name: Model override (default from env or nomic).
        dry_run: If True, compute embeddings but don't store.

    Returns:
        Dict with doc_id, num_chunks, num_embedded, and
        verification result.
    """
    from db.client import (
        get_chunks_for_document,
        get_document_by_doc_id,
    )
    from ingestion.verification import (
        save_verification_to_db,
        save_verification_to_registry,
        verify_embedding,
    )

    # 1. Look up the document
    doc = get_document_by_doc_id(doc_id)
    if not doc:
        raise ValueError(f"Document not found in DB: {doc_id}")
    document_id = doc["id"]

    # 2. Load existing chunks
    chunks = get_chunks_for_document(document_id)
    if not chunks:
        raise ValueError(
            f"No chunks in DB for {doc_id}. Run chunker first."
        )

    # 3. Filter to un-embedded chunks
    to_embed = [c for c in chunks if c.get("embedding") is None]
    log.info(
        "Document %s: %d total chunks, %d need embedding",
        doc_id, len(chunks), len(to_embed),
    )

    if not to_embed:
        log.info("All chunks already embedded for %s", doc_id)
        return {
            "doc_id": doc_id,
            "num_chunks": len(chunks),
            "num_embedded": len(chunks),
            "num_new": 0,
        }

    # 4. Embed locally (free — no budget check needed)
    embeddings = embed_document_chunks(
        to_embed, model_name=model_name
    )

    # 5. Store (unless dry run)
    num_stored = 0
    if not dry_run:
        chunk_indices = [c["chunk_index"] for c in to_embed]
        num_stored = store_embeddings(
            document_id, chunk_indices, embeddings
        )

    # 6. Verification
    num_total_embedded = len(chunks) - len(to_embed) + len(embeddings)
    vresult = verify_embedding(
        doc_id=doc_id,
        num_chunks=len(chunks),
        num_embedded=num_total_embedded,
        embedding_dim=EMBEDDING_DIM,
    )
    save_verification_to_registry(vresult)
    if not dry_run:
        save_verification_to_db(vresult, document_id)

    result = {
        "doc_id": doc_id,
        "num_chunks": len(chunks),
        "num_embedded": num_total_embedded,
        "num_new": len(embeddings),
        "num_stored": num_stored,
        "verification": vresult.result,
    }
    log.info(
        "Embedded %s: %d new vectors, verification=%s",
        doc_id, len(embeddings), vresult.result,
    )
    return result


# ════════════════════════════════════════════════
#  PIPELINE: Embed all documents
# ════════════════════════════════════════════════

def embed_all_documents(
    *,
    model_name: Optional[str] = None,
    dry_run: bool = False,
    skip_failed: bool = True,
) -> list[dict[str, Any]]:
    """
    Run the embedding pipeline for every active document in the DB.

    Args:
        model_name: Model override.
        dry_run: If True, don't store embeddings.
        skip_failed: If True, continue on errors.

    Returns:
        List of result dicts (one per document).
    """
    from db.client import list_documents

    docs = list_documents(status="active")
    log.info("Found %d active documents to embed", len(docs))

    results: list[dict[str, Any]] = []

    for doc in docs:
        doc_id = doc["doc_id"]
        try:
            r = embed_document(
                doc_id,
                model_name=model_name,
                dry_run=dry_run,
            )
            results.append(r)
        except Exception as exc:
            log.error("Failed to embed %s: %s", doc_id, exc)
            if not skip_failed:
                raise
            results.append({
                "doc_id": doc_id,
                "error": str(exc),
            })

    # Free model memory after batch job
    unload_model()

    # Summary
    embedded = sum(1 for r in results if "error" not in r)
    log.info("\n" + "=" * 50)
    log.info("Embedding complete")
    log.info("  Documents: %d/%d succeeded", embedded, len(results))
    log.info("=" * 50)

    return results


# ════════════════════════════════════════════════
#  CLI
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Embed document chunks via nomic-embed-text"
    )
    parser.add_argument(
        "doc_id",
        nargs="?",
        default=None,
        help="Document ID to embed (omit for all documents)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: nomic-ai/nomic-embed-text-v1.5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute embeddings but don't store in DB",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.doc_id:
        result = embed_document(
            args.doc_id,
            model_name=args.model,
            dry_run=args.dry_run,
        )
        print(f"\n{'='*50}")
        print(f"  doc_id      : {result['doc_id']}")
        print(f"  num_chunks  : {result['num_chunks']}")
        print(f"  num_embedded: {result['num_embedded']}")
        print(f"  num_new     : {result['num_new']}")
        print(f"  verification: {result.get('verification', 'n/a')}")
        print(f"{'='*50}")
    else:
        results = embed_all_documents(
            model_name=args.model,
            dry_run=args.dry_run,
        )
        passed = sum(
            1 for r in results
            if r.get("verification") == "pass"
        )
        print(f"\n  {passed}/{len(results)} documents embedded")
