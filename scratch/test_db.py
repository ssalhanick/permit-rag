import psycopg
import sys

connection_strings = [
    "postgresql://postgres:localdev@localhost:5433/permit_rag",
    "postgresql://postgres:localdev@localhost:5432/permit_rag",
    "postgresql://postgres:changeme@localhost:5433/permit_rag",
    "postgresql://postgres:changeme@localhost:5432/permit_rag",
    "postgresql://postgres:localdev@127.0.0.1:5433/permit_rag",
    "postgresql://postgres:localdev@127.0.0.1:5432/permit_rag",
]

for conn_str in connection_strings:
    print(f"Trying: {conn_str}")
    try:
        with psycopg.connect(conn_str, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                print("  SUCCESS!")
                sys.exit(0)
    except Exception as e:
        print(f"  FAILED: {e}")
