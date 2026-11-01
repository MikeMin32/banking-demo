"""Create a consistent SQLite snapshot for VPS transfer.

Uses the Python sqlite3 backup API so WAL contents are included.
Opens the live database read-only and never writes to it.

    PYTHONPATH=. python scripts/export_vps_snapshot.py

Output is written under data/transfers/ (gitignored). Do not commit it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import load_settings


def _counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY 1"
        )
    ]
    return {name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]) for name in tables}


def main() -> None:
    settings = load_settings()
    source_path = Path(settings.database_path).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"Database not found: {source_path}")

    dest_dir = source_path.parent / "transfers"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / "bank_manager-vps-snapshot.db"

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    dest = sqlite3.connect(dest_path)
    try:
        source.backup(dest)
        dest.commit()
        integrity = dest.execute("PRAGMA integrity_check").fetchone()[0]
        dest_counts = _counts(dest)
    finally:
        dest.close()
        source.close()

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    try:
        source_counts = _counts(source)
        source_integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        source.close()

    print(f"Source:    {source_path}")
    print(f"Snapshot:  {dest_path}")
    print(f"Size:      {dest_path.stat().st_size} bytes")
    print(f"Integrity: source={source_integrity} snapshot={integrity}")
    print(f"Counts:    {dest_counts}")
    if integrity != "ok" or source_integrity != "ok" or dest_counts != source_counts:
        raise SystemExit("Snapshot verification failed.")
    print("Verification passed. File is gitignored; do not commit or push it.")


if __name__ == "__main__":
    main()
