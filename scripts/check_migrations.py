"""
scripts/check_migrations.py — which migrations does this database have?
========================================================================
There is no schema_migrations table: scripts/apply_migration.py executes a
file and records nothing. So the only way to know what a given database has
is to probe for the artifacts each migration creates.

This matters whenever more than one database is in play -- a second dev
machine, Docker local vs RDS -- because nothing stops a migration being
applied out of order or skipped entirely.

Also reports corpus size, since an empty corpus makes RAGAs scores
meaningless (zero chunks retrieved scores as unfaithful) and that failure
looks identical to a quality regression.

Which database it targets is not obvious: `bootstrap_env` loads `.env` last
with ``override=True``, so a DATABASE_URL there beats `.env.local`, and all
three dotenv files are gitignored so the target differs per machine. The banner
below always names the host, and `--local` forces `.env.local`.

Usage:
    py scripts/check_migrations.py
    py scripts/check_migrations.py --local     # ignore .env / .env.production
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import dotenv_values

from api.load_env import bootstrap_env

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if "--local" in sys.argv:
    # Read .env.local directly so an override elsewhere cannot redirect us.
    _local = dotenv_values(PROJECT_ROOT / ".env.local")
    if not _local.get("DATABASE_URL"):
        print("--local: .env.local has no DATABASE_URL on this machine.")
        raise SystemExit(1)
    bootstrap_env()
    os.environ["DATABASE_URL"] = _local["DATABASE_URL"]
    PROFILE = "local (forced)"
else:
    PROFILE = bootstrap_env()

from db.client import get_conn

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")

# (migration, kind, target, column) -- probed in order.
#
# Two migrations share the number 026. The collision is recorded rather than
# corrected: both are already applied by name on multiple databases, and
# renaming an applied migration is riskier than the duplicate. Each is probed
# independently, so neither hides the other.
_PROBES: list[tuple[str, str, str, str | None]] = [
    ("018_design_intent_usage", "table", "design_intent_usage", None),
    ("019_project_gis_fields", "column", "projects", "latitude"),
    ("020_project_custom_prompt", "column", "projects", "custom_system_prompt"),
    ("021_project_materials", "column", "projects", "materials"),
    ("022_source_identity", "column", "documents", "source_url_normalized"),
    ("023_project_lifecycle", "column", "projects", "deleted_at"),
    ("024_global_roles", "column", "users", "role_synced_at"),
    ("025_project_delete_audit_log", "table", "project_delete_audit_log", None),
    ("026_agent_traces", "table", "agent_runs", None),
    # FK gains ON DELETE SET NULL (confdeltype 'n'); default 'a' = NO ACTION.
    (
        "026_design_intent_usage_project_fk",
        "sql",
        "SELECT EXISTS (SELECT 1 FROM pg_constraint "
        "WHERE conname = 'design_intent_usage_project_id_fkey' "
        "AND confdeltype = 'n') AS present;",
        None,
    ),
    # Dedupe fix: entity columns stop being nullable.
    (
        "027_agent_action_item_dedupe",
        "sql",
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'agent_action_items' "
        "AND column_name = 'entity_type' AND is_nullable = 'NO') AS present;",
        None,
    ),
]

_TABLE_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
    ) AS present;
"""

_COLUMN_SQL = """
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
    ) AS present;
"""


def _target_host() -> str:
    """Return the host:port portion of DATABASE_URL, or '(unset)'."""
    dsn = os.environ.get("DATABASE_URL", "")
    if "@" not in dsn:
        return "(unset)"
    return dsn.split("@", 1)[1].split("/", 1)[0]


def _is_local(host: str) -> bool:
    """True when the target looks like a developer machine."""
    return any(host.startswith(prefix) for prefix in _LOCAL_HOSTS)


def _banner(host: str) -> None:
    """Name the target loudly enough that prod is never mistaken for local."""
    if _is_local(host):
        print(f"Target: {host}  (profile={PROFILE})  — LOCAL\n")
        return
    print("=" * 70)
    print(f"  TARGET IS NOT LOCAL: {host}")
    print(f"  profile={PROFILE}")
    print("  Re-run with --local to inspect this machine's Docker database.")
    print("=" * 70)
    print()


def _probe(conn, kind: str, target: str, column: str | None) -> bool:
    """Return True when the artifact a migration creates is present."""
    if kind == "table":
        row = conn.execute(_TABLE_SQL, (target,)).fetchone()
    elif kind == "sql":
        row = conn.execute(target).fetchone()
    else:
        row = conn.execute(_COLUMN_SQL, (target, column)).fetchone()
    return bool(row and row["present"])


def _corpus_summary(conn) -> tuple[int, int, int]:
    """Return (documents, chunks, embedded chunks); zeros when tables absent."""
    try:
        docs = conn.execute("SELECT count(*) c FROM documents").fetchone()["c"]
        chunks = conn.execute("SELECT count(*) c FROM chunks").fetchone()["c"]
        embedded = conn.execute(
            "SELECT count(*) c FROM chunks WHERE embedding IS NOT NULL"
        ).fetchone()["c"]
        return int(docs), int(chunks), int(embedded)
    except Exception:
        return 0, 0, 0


def main() -> None:
    """Print migration status and corpus size for the configured database."""
    _banner(_target_host())

    with get_conn() as conn:
        results = [
            (name, _probe(conn, kind, target, column))
            for name, kind, target, column in _PROBES
        ]
        docs, chunks, embedded = _corpus_summary(conn)

    print("Migrations (probed by artifact -- there is no tracking table):")
    for name, present in results:
        print(f"  [{'x' if present else ' '}] {name}")

    missing = [name for name, present in results if not present]
    applied = [name for name, present in results if present]

    print(f"\nCorpus: {docs} documents, {chunks} chunks, {embedded} embedded")
    if chunks == 0:
        print("  ⚠ Empty corpus. RAGAs will score near zero because retrieval")
        print("    returns nothing -- that is not a quality regression.")

    if missing:
        print(f"\n⚠ Missing {len(missing)}:")
        for name in missing:
            print(f"    py scripts/apply_migration.py db/migrations/{name}.sql")
        # Out-of-order application is the failure this script exists to catch.
        if applied and missing:
            last_applied = applied[-1]
            if any(m < last_applied for m in missing):
                print("\n  ⚠ A migration is missing *behind* one that is applied.")
                print("    Apply in ascending order.")
    else:
        print("\n✅ All probed migrations present.")


if __name__ == "__main__":
    main()
