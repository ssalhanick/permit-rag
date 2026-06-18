import os
import sys
from dotenv import load_dotenv

# Add root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from db.client import get_conn

def apply_migration():
    migration_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "db", "migrations", "012_query_log_updates.sql"
    )
    
    with open(migration_path, "r") as f:
        sql = f.read()
        
    print("Executing migration DDL...")
    with get_conn() as conn:
        conn.execute(sql)
        conn.commit()
    print("Migration applied successfully!")

if __name__ == "__main__":
    apply_migration()
