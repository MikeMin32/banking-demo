"""Schema creation and versioned migrations.

Future schema changes belong in MIGRATIONS as a new (version, sql) pair.
Never edit an already-applied migration in place.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    holder_name TEXT,
    account_type TEXT,
    currency TEXT NOT NULL,
    balance_minor INTEGER NOT NULL DEFAULT 0,
    last_updated_at TEXT,
    last_checked_at TEXT,
    login_url TEXT,
    login_username TEXT,
    password_manager_ref TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_archived INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1))
);

CREATE TABLE IF NOT EXISTS deposit_details (
    account_id INTEGER PRIMARY KEY,
    account_holder TEXT,
    bank_name TEXT,
    iban TEXT,
    account_number TEXT,
    routing_number TEXT,
    sort_code TEXT,
    swift_bic TEXT,
    payment_reference TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS balance_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    old_balance_minor INTEGER NOT NULL,
    new_balance_minor INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expected_withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    amount_minor INTEGER NOT NULL,
    expected_date TEXT,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminder_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    reminder_time TEXT NOT NULL DEFAULT '09:00',
    stale_hours INTEGER NOT NULL DEFAULT 24,
    compact_overview INTEGER NOT NULL DEFAULT 0 CHECK (compact_overview IN (0, 1))
);

CREATE TABLE IF NOT EXISTS reminder_delivery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_date TEXT NOT NULL UNIQUE,
    sent_at TEXT NOT NULL,
    recipient_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_accounts_archived ON accounts(is_archived);
CREATE INDEX IF NOT EXISTS idx_accounts_currency ON accounts(currency);
CREATE INDEX IF NOT EXISTS idx_balance_history_account ON balance_history(account_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_withdrawals_account_status ON expected_withdrawals(account_id, status);
CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON expected_withdrawals(status);
"""

SCHEMA_V2 = """
CREATE INDEX IF NOT EXISTS idx_accounts_vm_number ON accounts(vm_number);
"""

MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
    (2, SCHEMA_V2),
]


async def init_schema(conn: aiosqlite.Connection) -> None:
    """Apply any unapplied migrations. Safe to call on every startup."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    await conn.commit()

    cursor = await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
    row = await cursor.fetchone()
    current = int(row[0]) if row else 0

    from app.utils.time import utc_now_iso

    pending = [item for item in MIGRATIONS if item[0] > current]
    if pending:
        await _backup_before_migration(conn, pending[0][0])

    for version, sql in pending:
        logger.info("applying schema migration version=%s", version)
        if version == 2:
            await _apply_v2(conn)
        if sql.strip():
            await conn.executescript(sql)
        await conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, utc_now_iso()),
        )
        await conn.commit()

    await _ensure_default_reminder_settings(conn)


async def _column_names(conn: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cursor.fetchall()
    return {row[1] for row in rows}


async def _add_column_if_missing(conn: aiosqlite.Connection, table: str, name: str, decl: str) -> None:
    if name not in await _column_names(conn, table):
        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


async def _apply_v2(conn: aiosqlite.Connection) -> None:
    """Add VM / company fields and backfill from existing display names and bank_name."""
    if "accounts" not in {
        row[0]
        for row in await (await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    }:
        return
    await _add_column_if_missing(conn, "accounts", "vm_number", "INTEGER")
    await _add_column_if_missing(conn, "accounts", "company_name", "TEXT")
    await _backfill_vm_fields(conn)


async def _backfill_vm_fields(conn: aiosqlite.Connection) -> None:
    from app.services.naming import parse_account_name, resolve_display_name

    cursor = await conn.execute("SELECT id, display_name, vm_number, company_name FROM accounts")
    rows = await cursor.fetchall()
    for row in rows:
        vm_number = row["vm_number"]
        company_name = row["company_name"]
        if vm_number is None or not company_name:
            parsed_vm, parsed_company = parse_account_name(row["display_name"])
            if vm_number is None:
                vm_number = parsed_vm
            if not company_name:
                company_name = parsed_company
        display_name = resolve_display_name(
            vm_number, company_name, fallback=row["display_name"]
        )
        await conn.execute(
            """
            UPDATE accounts
            SET vm_number = ?, company_name = ?, display_name = ?
            WHERE id = ?
            """,
            (vm_number, company_name, display_name, row["id"]),
        )
    await conn.commit()


async def _backup_before_migration(conn: aiosqlite.Connection, version: int) -> None:
    cursor = await conn.execute("PRAGMA database_list")
    rows = await cursor.fetchall()
    main = next((row for row in rows if row[1] == "main"), None)
    if main is None:
        return
    path = main[2]
    if not path or path == ":memory:":
        return
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return
    from app.utils.time import utc_now

    dest_dir = source.resolve().parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"pre-v{version}-{utc_now().strftime('%Y%m%d-%H%M%S')}.db"
    dest_conn = await aiosqlite.connect(dest)
    try:
        await conn.backup(dest_conn)
        await dest_conn.commit()
    finally:
        await dest_conn.close()
    logger.info("pre-migration backup created version=%s", version)


async def _ensure_default_reminder_settings(conn: aiosqlite.Connection) -> None:
    cursor = await conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='reminder_settings'"
    )
    if await cursor.fetchone() is None:
        return
    cursor = await conn.execute("SELECT 1 FROM reminder_settings WHERE id = 1")
    if await cursor.fetchone() is None:
        await conn.execute(
            """
            INSERT INTO reminder_settings (id, enabled, reminder_time, stale_hours, compact_overview)
            VALUES (1, 1, '09:00', 24, 0)
            """
        )
        await conn.commit()
