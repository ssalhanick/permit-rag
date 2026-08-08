"""
scripts/check_mckinney.py — verify McKinney/Frisco chunks landed, read-only.
 
Run with --local to force .env.local (this machine's corpus DB), matching
this project's own diagnostic scripts' pattern (see check_migration_details.py).
"""
 
from __future__ import annotations
 
import sys
from pathlib import Path
 
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
 
import _db_target
 
from api.load_env import bootstrap_env
 
TARGET = _db_target.resolve(sys.argv[1:], bootstrap_env)
 
from db.client import get_conn
 
_db_target.banner(TARGET)
_db_target.ensure_reachable(TARGET, get_conn)
 
with get_conn() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            select d.doc_id, d.municipality, d.document_status, length(c.content) as content_length
            from chunks c
            join documents d on d.id = c.document_id
            where d.municipality in ('mckinney', 'frisco')
            limit 10;
        """)
        rows = cur.fetchall()
        if not rows:
            print("No chunks found for mckinney/frisco.")
        for row in rows:
            print(row)
 
    with conn.cursor() as cur:
        cur.execute("""
            select doc_id, municipality, document_status, source_tier
            from documents
            where municipality in ('mckinney', 'frisco');
        """)
        rows = cur.fetchall()
        print()
        if not rows:
            print("No document rows at all for mckinney/frisco — nothing was ever uploaded.")
        for row in rows:
            print(row)