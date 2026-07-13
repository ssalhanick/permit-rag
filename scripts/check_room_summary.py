"""scripts/check_room_summary.py — verify room scan summaries synced to projects.room_summary."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.load_env import bootstrap_env

bootstrap_env()

from db.client import get_conn


def _mask_db_url(db_url: str) -> str:
    """Return DATABASE_URL with password redacted for logs."""
    if "@" not in db_url:
        return db_url
    creds, host = db_url.split("@", 1)
    user = creds.split(":")[0] if ":" in creds else creds
    return f"{user}:***@{host}"


def _print_rows(rows: list[dict]) -> None:
    """Print project rows with room_summary JSON."""
    if not rows:
        print("No projects with room_summary found.")
        return
    for row in rows:
        summary = row.get("room_summary")
        if isinstance(summary, str):
            summary = json.loads(summary)
        derived = (summary or {}).get("derived", {})
        print(f"- {row['name']} ({row['id']})")
        print(f"    captured_at: {(summary or {}).get('captured_at')}")
        print(f"    derived: {json.dumps(derived)}")


def main() -> None:
    """Check migration 015 column and list synced room summaries."""
    project_id = sys.argv[1] if len(sys.argv) > 1 else None
    db_url = os.environ.get("DATABASE_URL", "")
    print(f"DATABASE_URL → {_mask_db_url(db_url) or 'NOT SET'}")

    with get_conn() as conn:
        column = conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'projects'
              AND column_name = 'room_summary';
            """
        ).fetchone()
        if not column:
            print("FAIL: projects.room_summary column missing (apply migration 015).")
            sys.exit(1)
        print("OK: projects.room_summary column exists.")

        if project_id:
            rows = conn.execute(
                """
                SELECT id, name, room_summary
                FROM projects
                WHERE id = %(id)s::uuid;
                """,
                {"id": project_id},
            ).fetchall()
            if not rows:
                print(f"FAIL: project not found: {project_id}")
                sys.exit(1)
            if not rows[0].get("room_summary"):
                print(f"FAIL: project {project_id} has no room_summary yet.")
                sys.exit(1)
            print(f"OK: project {project_id} has room_summary:")
            _print_rows(rows)
            sys.exit(0)

        rows = conn.execute(
            """
            SELECT id, name, room_summary
            FROM projects
            WHERE room_summary IS NOT NULL
            ORDER BY room_summary->>'captured_at' DESC NULLS LAST;
            """
        ).fetchall()
        print(f"\nProjects with room_summary: {len(rows)}")
        _print_rows(rows)
        if not rows:
            print(
                "\nHint: mobile prod uses RDS. Run with ENVIRONMENT=production "
                "and .env.production DATABASE_URL, or scan again from the app."
            )
            sys.exit(1)
        sys.exit(0)


if __name__ == "__main__":
    main()
