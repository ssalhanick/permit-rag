"""
scripts/seed_langsmith_security_fixture.py — seed the project-isolation test fixture
======================================================================================
Creates the private (tier-3) test document that
evaluation/langsmith_datasets/permit_rag_security_v1.json's
project_isolation_regression case needs to stop self-skipping (see that
example's own "PLACEHOLDER, not yet runnable" notes for the exact spec this
follows).

Plants clearly-fake, obviously-labeled content -- not real permit code.
Idempotent (insert_document/insert_chunks both upsert on conflict), safe to
re-run. Uses scripts/_db_target.py's safety pattern: never guesses a target,
prints a banner naming the real host before writing anything.

CAUTION: this writes a fake document into whatever corpus DB you point it at.
Only ever run against a local/campus dev corpus -- never prod. The banner
below names the host every time; read it before confirming.

    py scripts/seed_langsmith_security_fixture.py --local              # dry-run
    py scripts/seed_langsmith_security_fixture.py --local --apply      # writes
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

# Synthetic, clearly-fake IDs -- never real project/user identities. Mirrors
# the existing dataset placeholder's own convention (see permit_rag_security_v1
# .json's committed example, which already uses an all-zeros querying project).
OWNER_PROJECT_ID = UUID("00000000-0000-0000-0000-0000000000aa")
QUERYING_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")

DOC_ID = "test-fixture-cross-project-isolation-v1"
_FIXTURE_CONTENT = (
    "TEST FIXTURE -- NOT A REAL PERMIT DOCUMENT. This paragraph exists only to "
    "validate permit_rag_security_v1's project_isolation_regression evaluator "
    "(evaluation/langsmith_eval.py). It confirms a tier-3 private document "
    "belonging to one project never surfaces in a different project's query "
    "answers. Canary marker for this test: XYZZY-ISOLATION-CANARY-7f3a."
)


def seed(*, apply: bool) -> str:
    """Insert (or update) the fixture project's private document + chunk +
    embedding. Returns the doc_id. Prints what it would do when not applying."""
    if not apply:
        print(f"Would insert document {DOC_ID!r}")
        print(f"  owner_project_id = {OWNER_PROJECT_ID}  (visibility='private', source_tier=3)")
        print(f"  {len(_FIXTURE_CONTENT)} chars of fixture content, 1 chunk, embedded locally")
        print("\nDry run -- nothing written. Re-run with --apply to seed for real.")
        return DOC_ID

    from db import client as db_client

    doc = db_client.insert_document(
        doc_id=DOC_ID,
        source_url="https://example.invalid/test-fixture",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=["test-fixture"],
        document_status="active",
        source_tier=3,
        project_id=OWNER_PROJECT_ID,
        visibility="private",
    )
    print(f"Document row ready: id={doc['id']} doc_id={DOC_ID!r}")

    db_client.insert_chunks(doc["id"], [{
        "chunk_index": 0,
        "content": _FIXTURE_CONTENT,
        "char_count": len(_FIXTURE_CONTENT),
    }])
    print("Chunk inserted.")

    from ingestion.embedder import embed_document

    result = embed_document(DOC_ID, force=True)
    print(f"Embedded: {result}")
    return DOC_ID


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed the project_isolation_regression LangSmith test fixture."
    )
    parser.add_argument("--local", action="store_true", help="Force .env.local target.")
    parser.add_argument("--database-url", help="Explicit DATABASE_URL (bypasses dotenv).")
    parser.add_argument("--apply", action="store_true", help="Write for real (default: dry-run).")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    target = _db_target.resolve(sys.argv[1:], bootstrap_env)
    _db_target.banner(target, read_only=not args.apply)
    _db_target.ensure_reachable(target)

    doc_id = seed(apply=args.apply)

    if args.apply:
        print(f"\nNext: set permit_rag_security_v1.json's expected_forbidden_chunk_doc_ids "
              f"to [{doc_id!r}], point inputs.project_id at {QUERYING_PROJECT_ID} (a "
              f"different project than the fixture's owner {OWNER_PROJECT_ID}), remove "
              f"requires_seed_data, then re-sync with "
              f"py -m evaluation.langsmith_upsert_dataset "
              f"--file evaluation/langsmith_datasets/permit_rag_security_v1.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
