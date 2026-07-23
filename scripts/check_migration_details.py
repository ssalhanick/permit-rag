"""
scripts/check_migration_details.py — verify migration *contents*, not presence
==============================================================================
`check_migrations.py` answers "was this migration applied?". This answers
"was the *right version* applied, and did the follow-up work happen?" -- the
questions that matter once a migration has already reached a database.

READ-ONLY. Issues no writes and opens no transaction that mutates anything.
Safe to point at production.

Checks:
  026_agent_traces  — is the action-queue dedupe fix present? A nullable
                      entity_type means the earlier version was applied, where
                      NULLs never conflict in a unique index so entity-less
                      items silently skipped dedupe.
  022_source_identity — are the identity columns actually backfilled? The
                      migration only adds columns; scripts/backfill_source_identity.py
                      populates them, and a database can have one without the other.

Usage:
    py scripts/check_migration_details.py
    py scripts/check_migration_details.py --local
    py scripts/check_migration_details.py --database-url='postgresql://...'
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

from db.client import get_conn


def _table_exists(conn: Any, name: str) -> bool:
    """True when a public table of this name exists."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=%s) AS present;",
        (name,),
    ).fetchone()
    return bool(row and row["present"])


def _column_exists(conn: Any, table: str, column: str) -> bool:
    """True when a column exists on a public table."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s AND column_name=%s) AS present;",
        (table, column),
    ).fetchone()
    return bool(row and row["present"])


def check_026(conn: Any) -> list[str]:
    """Report whether the applied 026 includes the dedupe fix."""
    print("── 026_agent_traces ─────────────────────────────────────────")
    if not _table_exists(conn, "agent_runs"):
        print("  not applied to this database")
        print("    → py scripts/apply_migration.py db/migrations/026_agent_traces.sql\n")
        return []

    actions: list[str] = []
    nullable = conn.execute(
        "SELECT column_name, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_name='agent_action_items' "
        "AND column_name IN ('entity_type','entity_id') "
        "ORDER BY column_name;"
    ).fetchall()

    for row in nullable:
        state = "NULL allowed" if row["is_nullable"] == "YES" else "NOT NULL"
        default = row["column_default"] or "none"
        print(f"  agent_action_items.{row['column_name']:<12} {state:<12} default={default}")

    buggy = any(r["is_nullable"] == "YES" for r in nullable)
    if buggy:
        print("\n  ⚠ BUGGY VERSION APPLIED")
        print("    Entity-less action items skip dedupe: NULLs never conflict in a")
        print("    unique index, so a nightly anomaly sweep will pile up duplicates.")
        actions.append(
            "py scripts/apply_migration.py "
            "db/migrations/027_agent_action_item_dedupe.sql"
        )
    elif nullable:
        print("\n  ✅ dedupe fix present")

    idx = conn.execute(
        "SELECT indexdef FROM pg_indexes "
        "WHERE tablename='agent_action_items' "
        "AND indexname='uq_agent_action_items_open_entity';"
    ).fetchone()
    print(f"  dedupe index : {'present' if idx else 'MISSING'}")
    if not idx:
        actions.append("uq_agent_action_items_open_entity is missing — dedupe is off entirely.")

    counts = conn.execute(
        "SELECT (SELECT count(*) FROM agent_runs)  AS runs, "
        "       (SELECT count(*) FROM agent_steps) AS steps, "
        "       (SELECT count(*) FROM agent_action_items) AS items;"
    ).fetchone()
    print(f"  rows         : {counts['runs']} runs, {counts['steps']} steps, "
          f"{counts['items']} action items")
    if buggy and counts["runs"] == 0:
        print("  note         : tables are empty, so a corrective 027 carries no data risk")
    print()
    return actions


def check_022(conn: Any) -> list[str]:
    """Report whether 022's identity columns were backfilled."""
    print("── 022_source_identity ──────────────────────────────────────")
    if not _column_exists(conn, "documents", "source_url_normalized"):
        print("  not applied to this database")
        print("    → py scripts/apply_migration.py db/migrations/022_source_identity.sql\n")
        return []

    row = conn.execute(
        "SELECT count(*) AS total, "
        "       count(*) FILTER (WHERE source_url_normalized IS NULL) AS unbackfilled "
        "FROM documents;"
    ).fetchone()
    total, missing = int(row["total"]), int(row["unbackfilled"])
    print("  applied      : yes")
    print(f"  documents    : {total}")
    print(f"  unbackfilled : {missing}")

    actions: list[str] = []
    if total == 0:
        print("  (no corpus here, so nothing to backfill)")
    elif missing:
        print(f"\n  ⚠ {missing}/{total} documents have no normalized source URL.")
        print("    The migration adds columns; the backfill populates them.")
        actions.append("py scripts/backfill_source_identity.py")
    else:
        print("\n  ✅ fully backfilled")
    print()
    return actions


def main() -> None:
    """Run every content check and print a consolidated action list."""
    _db_target.banner(TARGET)
    _db_target.ensure_reachable(TARGET, get_conn)
    with get_conn() as conn:
        actions = check_026(conn) + check_022(conn)

    if not actions:
        print("✅ Nothing to do on this database.")
        return

    print("Actions needed:")
    for i, action in enumerate(actions, 1):
        print(f"  {i}. {action}")


if __name__ == "__main__":
    main()
