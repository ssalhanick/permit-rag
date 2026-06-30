"""scripts/check_schema.py — diagnostic: show users table columns and DB URL."""
import os
from api.load_env import bootstrap_env

bootstrap_env()

db_url = os.environ.get("DATABASE_URL", "NOT SET")
# Mask password for safe display
if "@" in db_url:
    parts = db_url.split("@")
    creds, host = parts[0], parts[1]
    masked = creds.split(":")[0] + ":***@" + host
else:
    masked = db_url

print(f"DATABASE_URL → {masked}")

from db.client import get_conn

with get_conn() as conn:
    rows = conn.execute(
        "SELECT column_name, data_type, is_nullable "
        "FROM information_schema.columns "
        "WHERE table_name = 'users' "
        "ORDER BY ordinal_position;"
    ).fetchall()

print("\nusers table columns:")
for r in rows:
    print(f"  {r['column_name']:30s} {r['data_type']:20s} nullable={r['is_nullable']}")
