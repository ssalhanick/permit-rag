"""
scripts/seed_langsmith_security_fixture.py — seed the project-isolation test fixture
======================================================================================
Creates the tier-3 test document that
evaluation/langsmith_datasets/permit_rag_security_v1.json's
project_isolation_regression case needs to stop self-skipping (see that
example's own "PLACEHOLDER, not yet runnable" notes for the exact spec this
follows).

Plants clearly-fake, obviously-labeled content -- not real permit code.
Idempotent (looks up its synthetic user/project/document by fixed
identifiers before creating anything), safe to re-run. Uses
scripts/_db_target.py's safety pattern: never guesses a target, prints a
banner naming the real host before writing anything.

``visibility='team'``, not ``'private'`` -- deliberately.
``langsmith_eval.py``'s ``run_pipeline()`` never passes ``requesting_user_id``
to ``retrieve_with_project`` (always ``None``), and
``db.client.match_project_chunks()`` only shows a ``'private'`` tier-3 doc
when ``requesting_user_id`` matches ``uploaded_by``. A ``'private'`` fixture
would be excluded unconditionally regardless of ``project_id``, making the
isolation check pass vacuously -- it would never actually exercise the
project boundary this test exists to catch a regression in. ``'team'`` docs
are scoped by ``project_id`` alone, which is the actual property under test.

CAUTION: this writes fake user/project/document rows into whatever corpus DB
you point it at. Only ever run against a local/campus dev corpus -- never
prod. The banner below names the host every time; read it before confirming.

    py scripts/seed_langsmith_security_fixture.py --local              # dry-run
    py scripts/seed_langsmith_security_fixture.py --local --apply      # writes
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

# Fixed, recognizable identifiers used to find-or-create the fixture
# idempotently. The owner project's real id is server-generated
# (db.client.create_project has no caller-supplied-UUID path) and looked up
# by this name on every run rather than hardcoded.
OWNER_COGNITO_SUB = "test-fixture-langsmith-security-owner"
OWNER_EMAIL = "test-fixture-langsmith-security@example.invalid"
OWNER_PROJECT_NAME = "TEST FIXTURE -- project isolation regression (do not delete)"

# The querying side needs no real row: it's only ever used as a WHERE-clause
# filter value in match_project_chunks, never the target of an insert, so a
# synthetic UUID with no backing project row is fine -- it just correctly
# matches nothing of its own.
QUERYING_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")

DOC_ID = "test-fixture-cross-project-isolation-v1"
_FIXTURE_CONTENT = (
    "TEST FIXTURE -- NOT A REAL PERMIT DOCUMENT. This paragraph exists only to "
    "validate permit_rag_security_v1's project_isolation_regression evaluator "
    "(evaluation/langsmith_eval.py). It confirms a tier-3 document belonging "
    "to one project never surfaces in a different project's query answers. "
    "Canary marker for this test: XYZZY-ISOLATION-CANARY-7f3a."
)


def _get_or_create_owner_project(db_client: Any) -> UUID:
    """Find the fixture's owner project by its fixed name, or create it (and
    its synthetic owner user) on first run. Returns the project id."""
    user = db_client.get_or_create_cognito_user(
        OWNER_COGNITO_SUB, OWNER_EMAIL, display_name="Test Fixture Owner"
    )

    with db_client.get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM projects WHERE name = %s AND owner_user_id = %s;",
            (OWNER_PROJECT_NAME, user["id"]),
        ).fetchone()
    if row:
        return row["id"]

    project = db_client.create_project(name=OWNER_PROJECT_NAME, owner_user_id=user["id"])
    return project["id"]


def seed(*, apply: bool) -> str:
    """Insert (or update) the fixture project's document + chunk + embedding.
    Returns the doc_id. Prints what it would do when not applying."""
    if not apply:
        print(f"Would get-or-create user {OWNER_EMAIL!r} and project {OWNER_PROJECT_NAME!r}")
        print(f"Would insert document {DOC_ID!r} under that project "
              f"(visibility='team', source_tier=3)")
        print(f"  {len(_FIXTURE_CONTENT)} chars of fixture content, 1 chunk, embedded locally")
        print("\nDry run -- nothing written. Re-run with --apply to seed for real.")
        return DOC_ID

    from db import client as db_client

    owner_project_id = _get_or_create_owner_project(db_client)
    print(f"Owner project ready: id={owner_project_id}")

    doc = db_client.insert_document(
        doc_id=DOC_ID,
        source_url="https://example.invalid/test-fixture",
        municipality="dallas",
        authority_level="municipal",
        doc_type="building_code",
        subject_tags=["test-fixture"],
        document_status="active",
        source_tier=3,
        project_id=owner_project_id,
        visibility="team",
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
        print(f"\ndoc_id is fixed and already matches permit_rag_security_v1.json's "
              f"expected_forbidden_chunk_doc_ids: {doc_id!r}. Querying project_id in "
              f"that dataset ({QUERYING_PROJECT_ID}) is intentionally a different, "
              f"real-row-free project than the fixture's owner -- that's the boundary "
              f"under test. Next: re-sync the dataset with "
              f"py -m evaluation.langsmith_upsert_dataset "
              f"--file evaluation/langsmith_datasets/permit_rag_security_v1.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
