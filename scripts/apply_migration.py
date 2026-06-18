"""
scripts/apply_migration.py — Utility to apply SQL migrations using connection pool
===================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from db.client import get_conn


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: py scripts/apply_migration.py <path_to_sql>")
        sys.exit(1)

    sql_path = Path(sys.argv[1])
    if not sql_path.exists():
        print(f"File not found: {sql_path}")
        sys.exit(1)

    print(f"Applying migration: {sql_path}")
    sql_content = sql_path.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.execute(sql_content)
        conn.commit()
    print("Migration applied successfully.")


if __name__ == "__main__":
    main()
