"""Apply the three VM demo accounts to the bot's configured SQLite database.

Does not run on startup. Safe to execute more than once.

    PYTHONPATH=. .venv/bin/python scripts/seed_demo_accounts.py
"""

from __future__ import annotations

import asyncio

from app.config import load_settings
from app.services.demo_accounts import apply_demo_accounts


async def main() -> None:
    settings = load_settings()
    report = await apply_demo_accounts(settings)
    print(f"Database: {report.database_path}")
    print(f"Backup:   {report.backup_path}")
    print("Created:", ", ".join(report.created) or "—")
    print("Updated:", ", ".join(report.updated) or "—")
    print("Removed:", ", ".join(report.removed) or "—")
    print("Preserved:", ", ".join(report.preserved) or "—")
    print("Withdrawals upserted:", report.withdrawals_upserted)
    print("History written:", report.history_written)
    print("Activity skipped:", ", ".join(report.activity_skipped) or "—")


if __name__ == "__main__":
    asyncio.run(main())
