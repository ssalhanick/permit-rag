"""
scripts/init_rds_db.py — Fully bootstrap and migrate the production RDS database
================================================================================
Usage:
    1. Temporarily set DATABASE_URL in .env to the RDS connection string, e.g.:
       DATABASE_URL=postgresql://postgres:<your_db_password>@<rds_endpoint_address>:5432/permit_rag
    2. Run:
       py scripts/init_rds_db.py
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environmental variables from .env
load_dotenv()

# We need to import get_conn after load_dotenv so that psycopg connects to the right DATABASE_URL
from db.client import get_conn


def apply_sql_file(file_path: Path) -> None:
    print(f"Applying: {file_path.relative_to(Path.cwd())}...")
    sql_content = file_path.read_text(encoding="utf-8")
    
    # Simple split to execute commands individually (helps with role setup DO blocks)
    with get_conn() as conn:
        conn.execute(sql_content)
        conn.commit()


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or "localhost" in db_url or "127.0.0.1" in db_url:
        print("WARNING: DATABASE_URL points to localhost/127.0.0.1.")
        print("If you want to initialize the RDS instance, please set DATABASE_URL in your .env to the RDS endpoint first.")
        confirm = input("Do you still want to proceed with local database initialization? (y/n): ")
        if confirm.lower() != 'y':
            print("Aborted.")
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
