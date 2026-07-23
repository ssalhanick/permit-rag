"""
scripts/apply_migration.py — Utility to apply SQL migrations using connection pool
===================================================================================
Prints the target database before applying, and refuses to touch a non-local
host without explicit confirmation.

That guard exists because `api/load_env.py::bootstrap_env` loads `.env` last
with ``override=True``, so a DATABASE_URL there silently beats `.env.local` --
and all three dotenv files are gitignored, so the target differs per machine.
Without a banner, "Migration applied successfully." looks identical whether it
hit Docker or production RDS.

Usage:
    py scripts/apply_migration.py db/migrations/026_agent_traces.sql
    py scripts/apply_migration.py <path> --yes     # skip the prompt (CI)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.load_env import bootstrap_env, resolve_environment

PROFILE = bootstrap_env()

from db.client import get_conn

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")


def target_host() -> str:
    """Return the host:port portion of DATABASE_URL, or '(unset)'."""
    dsn = os.environ.get("DATABASE_URL", "")
    if "@" not in dsn:
        return "(unset)"
    return dsn.split("@", 1)[1].split("/", 1)[0]


def is_local(host: str) -> bool:
    """True when the target looks like a developer machine."""
    return any(host.startswith(prefix) for prefix in _LOCAL_HOSTS)


def confirm_remote(host: str, sql_path: Path) -> bool:
    """Ask before writing to anything that is not localhost."""
    print()
    print("  ******************************************************************")
    print("  *  This is NOT a local database.                                 *")
    print(f"  *  Target : {host:<51}*")
    print(f"  *  Profile: {PROFILE:<51}*")
    print(f"  *  Migration: {sql_path.name:<49}*")
    print("  *                                                                *")
    print("  *  AGENTS.md: a migration must never be modified once deployed.  *")
    print("  *  Applying here freezes this file's contents.                   *")
    print("  ******************************************************************")
    print()
    answer = input(f"  Type the host to continue ({host}): ").strip()
    return answer == host


def main() -> None:
    """Apply one migration file to the configured database."""
    args = [a for a in sys.argv[1:] if a != "--yes"]
    assume_yes = "--yes" in sys.argv[1:]

    if not args:
        print("Usage: py scripts/apply_migration.py <path_to_sql> [--yes]")
        sys.exit(1)

    sql_path = Path(args[0])
    if not sql_path.exists():
        print(f"File not found: {sql_path}")
        sys.exit(1)

    host = target_host()
    print(f"Target database : {host}  (profile={PROFILE}, ENVIRONMENT={resolve_environment()})")
    print(f"Applying migration: {sql_path}")

    if not is_local(host) and not assume_yes and not confirm_remote(host, sql_path):
        print("Aborted — nothing applied.")
        sys.exit(1)

    sql_content = sql_path.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql_content)
        conn.commit()
    print(f"Migration applied successfully to {host}.")


if __name__ == "__main__":
    main()
