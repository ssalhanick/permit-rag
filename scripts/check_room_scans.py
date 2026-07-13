"""scripts/check_room_scans.py — verify multi-scan summaries in project_room_scans."""

from __future__ import annotations

import argparse
import json
import os
import sys

from db.client import get_conn, ping


def _print_rows(rows: list[dict]) -> None:
    """Print scan rows without surfaces."""
    if not rows:
        print("No project_room_scans rows found.")
        return
    for row in rows:
        derived = row.get("derived") or {}
        if "surfaces" in derived:
            print(f"WARN: row {row['id']} derived contains surfaces (privacy violation).")
        print(
            f"- {row['scan_type']:9} {row['room_label']:20} "
            f"active={row['is_active']} parent={row.get('parent_scan_id')}"
        )
        print(f"  derived: {json.dumps(derived)}")


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Check project_room_scans table.")
    parser.add_argument("project_id", nargs="?", help="Optional project UUID filter")
    args = parser.parse_args()

    if not ping():
        print("FAIL: database unreachable.")
        return 1

    with get_conn() as conn:
        exists = conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'project_room_scans';
            """
        ).fetchone()
        if not exists:
            print("FAIL: project_room_scans missing (apply migration 016).")
            return 1
        print("OK: project_room_scans table exists.")

        if args.project_id:
            rows = conn.execute(
                """
                SELECT *
                FROM project_room_scans
                WHERE project_id = %s
                ORDER BY captured_at DESC;
                """,
                (args.project_id,),
            ).fetchall()
            print(f"\nScans for project {args.project_id}: {len(rows)}")
            _print_rows(rows)
            return 0

        rows = conn.execute(
            """
            SELECT project_id, scan_type, room_label, is_active, derived
            FROM project_room_scans
            ORDER BY captured_at DESC
            LIMIT 20;
            """
        ).fetchall()
        print(f"\nRecent scans (max 20): {len(rows)}")
        _print_rows(rows)
    return 0


if __name__ == "__main__":
    if os.environ.get("ENVIRONMENT") == "production":
        from api.load_env import bootstrap_env

        bootstrap_env()
    sys.exit(main())
