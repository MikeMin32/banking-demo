"""Online SQLite backup using the SQLite backup API."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

from app.database.connection import Database
from app.utils.time import utc_now


async def backup_database(db: Database, dest_dir: str | Path) -> Path:
    """Create a consistent snapshot while the bot is running."""
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().strftime("%Y%m%d-%H%M%S")
    dest_path = directory / f"bank_manager-{stamp}.db"
    dest = await aiosqlite.connect(dest_path)
    try:
        await db.conn.backup(dest)
        await dest.commit()
    finally:
        await dest.close()
    return dest_path
