"""
scripts/init_rds_db.py — bootstrap a database from scratch: extensions, schema,
roles, every migration in order, then seeds
================================================================================
*** THIS DROPS THE PUBLIC SCHEMA FIRST. Every table and row is destroyed. ***

Use it on an empty or disposable database. To add migrations to a database that
already holds data, use scripts/apply_migration.py one file at a time.

Usage:
    py scripts/init_rds_db.py                     # target from bootstrap_env
    py scripts/init_rds_db.py --local             # force .env.local
    py scripts/init_rds_db.py --database-url=...  # explicit target
    py scripts/init_rds_db.py --yes               # skip confirmation (CI)

Safety note: this script previously prompted only when the target *was*
localhost, so a remote host -- production RDS included -- was wiped with no
confirmation at all. The check is now the other way round: any non-local target
requires the hostname to be typed back.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable when invoked as `py scripts/init_rds_db.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _db_target

from api.load_env import bootstrap_env

TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)

from db.client import get_conn


def apply_sql_file(file_path: Path) -> None:
    print(f"Applying: {file_path.relative_to(Path.cwd())}...")
    sql_content = file_path.read_text(encoding="utf-8")
    
    # Simple split to execute commands individually (helps with role setup DO blocks)
    with get_conn() as conn:
        conn.execute(sql_content)
        conn.commit()


def confirm_destructive() -> bool:
    """
    Gate the schema drop on an explicit, target-aware confirmation.

    Remote targets must have their hostname typed back; localhost accepts y/n.
    Deliberately stricter the further the target is from this machine.
    """
    print()
    print("  " + "!" * 68)
    print("  !  DROP SCHEMA public CASCADE — every table and row is destroyed.")
    print(f"  !  Target: {TARGET.host}")
    print(f"  !  Source: {TARGET.source}")
    print("  " + "!" * 68)
    print()

    if TARGET.is_local:
        return input("  Wipe and rebuild this local database? (y/n): ").strip().lower() == "y"

    print("  This is NOT this machine. If it is production, its corpus and every")
    print("  user, project, and query log will be destroyed and not recoverable")
    print("  from this script.")
    print()
    return input(f"  Type the hostname to confirm ({TARGET.host}): ").strip() == TARGET.host


def main() -> None:
    """Wipe and rebuild the target database from schema + migrations + seeds."""
    _db_target.banner(TARGET, read_only=False)
    _db_target.ensure_reachable(TARGET)

    if "--yes" not in sys.argv and not confirm_destructive():
        print("Aborted — nothing changed.")
        return

    print("Wiping public schema for a clean bootstrap...")
    with get_conn() as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        conn.commit()

    print("Starting database initialization and migrations...")
    
    root_dir = Path(__file__).parent.parent
    
    # 1. Apply Extensions
    extensions_path = root_dir / "db" / "init" / "01_extensions.sql"
    if extensions_path.exists():
        apply_sql_file(extensions_path)
    
    # 2. Apply Schema
    schema_path = root_dir / "db" / "schema.sql"
    if schema_path.exists():
        apply_sql_file(schema_path)

    # 3. Apply Roles
    roles_path = root_dir / "db" / "init" / "02_roles.sql"
    if roles_path.exists():
        apply_sql_file(roles_path)

    # 4. Apply Migrations in Order
    migrations_dir = root_dir / "db" / "migrations"
    if migrations_dir.exists():
        migration_files = sorted(migrations_dir.glob("*.sql"))
        for mig in migration_files:
            apply_sql_file(mig)

    # 5. Apply Seed Data
    seeds_dir = root_dir / "db" / "seeds"
    if seeds_dir.exists():
        seed_files = sorted(seeds_dir.glob("*.sql"))
        for seed in seed_files:
            apply_sql_file(seed)

    print("\nDatabase bootstrapping completed successfully!")


if __name__ == "__main__":
    main()
