"""scripts/run_migration.py — apply a single SQL migration file via db.client."""

import sys
from db.client import get_conn
from api.load_env import bootstrap_env

bootstrap_env()

if len(sys.argv) < 2:
    print("Usage: py scripts/run_migration.py <filename.sql>")
    sys.exit(1)

migration_file = sys.argv[1]
with open(migration_file) as f:
    sql = f.read()

# psycopg3 execute() runs one statement at a time — split on semicolons.
# Strip comment lines from each chunk before checking if it has real SQL.
def _strip_comments(chunk: str) -> str:
    lines = [ln for ln in chunk.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()

statements = [_strip_comments(s) for s in sql.split(";") if _strip_comments(s)]

with get_conn() as conn:
    for stmt in statements:
        print(f"  → {stmt[:80]}...")
        conn.execute(stmt)
    conn.commit()

print(f"Applied: {migration_file}")
