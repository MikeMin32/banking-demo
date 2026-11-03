from __future__ import annotations

from app.database.connection import Database
from app.database.repositories.accounts import AccountRepository
from app.database.repositories.balances import BalanceRepository
from app.database.schema import SCHEMA_V1
from app.utils.time import utc_now_iso


async def test_v2_migration_parses_vm_names_and_keeps_links(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    import aiosqlite

    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA_V1)
    now = utc_now_iso()
    await conn.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    await conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)", (now,))
    await conn.execute(
        """
        INSERT INTO accounts (
            display_name, bank_name, holder_name, account_type, currency,
            balance_minor, last_updated_at, last_checked_at, created_at, updated_at, is_archived
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        ("VM 9 - LeBon Shoppe", "Airwallex", "Ada", "Business", "EUR", 245000, now, now, now, now),
    )
    await conn.execute(
        """
        INSERT INTO accounts (
            display_name, bank_name, currency, balance_minor, created_at, updated_at, is_archived
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        ("Operating", "Chase", "USD", 10000, now, now),
    )
    await conn.execute(
        "INSERT INTO balance_history (account_id, old_balance_minor, new_balance_minor, recorded_at) VALUES (1, 200000, 245000, ?)",
        (now,),
    )
    await conn.execute(
        """
        INSERT INTO expected_withdrawals (
            account_id, amount_minor, description, status, created_at, updated_at
        ) VALUES (1, 5000, 'rent', 'pending', ?, ?)
        """,
        (now, now),
    )
    await conn.commit()
    await conn.close()

    db = Database(str(path))
    await db.connect()
    await db.init()
    repo = AccountRepository(db)
    first = await repo.get(1)
    second = await repo.get(2)
    assert first is not None and second is not None
    assert first.id == 1
    assert first.vm_number == 9
    assert first.company_name == "LeBon Shoppe"
    assert first.display_name == "VM 9 - LeBon Shoppe"
    assert first.banking_provider == "Airwallex"
    assert second.vm_number is None
    assert second.company_name == "Operating"
    assert second.display_name == "Operating"
    assert second.banking_provider == "Chase"

    history = BalanceRepository(db)
    entries = await history.list_for_account(1)
    assert len(entries) == 1
    assert entries[0].account_id == 1

    row = await db.fetchone("SELECT COUNT(*) AS n FROM expected_withdrawals WHERE account_id = 1")
    assert int(row["n"]) == 1
    await db.init()
    again = await repo.get(1)
    assert again is not None
    assert again.display_name == "VM 9 - LeBon Shoppe"
    await db.close()


async def test_v3_adds_fields_without_overwriting_legacy(tmp_path) -> None:
    path = tmp_path / "legacy-v2.db"
    import aiosqlite

    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA_V1)
    now = utc_now_iso()
    await conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    await conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)", (now,))
    await conn.execute(
        """
        INSERT INTO accounts (
            display_name, bank_name, currency, balance_minor, created_at, updated_at, is_archived
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        ("VM 9 - LeBon Shoppe", "Airwallex", "EUR", 245000, now, now),
    )
    await conn.execute(
        """
        INSERT INTO deposit_details (account_id, iban, updated_at)
        VALUES (1, 'DE89370400440532013000', ?)
        """,
        (now,),
    )
    await conn.execute(
        """
        INSERT INTO expected_withdrawals (
            account_id, amount_minor, description, status, created_at, updated_at, completed_at
        ) VALUES (1, 5000, 'rent', 'completed', ?, ?, ?)
        """,
        (now, now, now),
    )
    await conn.commit()
    await conn.close()

    db = Database(str(path))
    await db.connect()
    await db.init()
    repo = AccountRepository(db)
    account = await repo.get(1)
    assert account is not None
    assert account.vm_number == 9
    assert account.company_name == "LeBon Shoppe"
    assert account.iban == "DE89370400440532013000"
    assert account.line_name is None
    assert account.linked_vm is None
    row = await db.fetchone("SELECT applied_to_balance, status FROM expected_withdrawals WHERE id = 1")
    assert int(row["applied_to_balance"]) == 0
    assert row["status"] == "completed"
    version = await db.fetchone("SELECT MAX(version) AS v FROM schema_migrations")
    assert int(version["v"]) >= 3
    await db.close()


async def test_v4_adds_top_ups_table(tmp_path) -> None:
    path = tmp_path / "pre-v4.db"
    import aiosqlite

    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA_V1)
    now = utc_now_iso()
    await conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    await conn.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (1, ?)", (now,))
    await conn.commit()
    await conn.close()

    db = Database(str(path))
    await db.connect()
    await db.init()
    version = await db.fetchone("SELECT MAX(version) AS v FROM schema_migrations")
    assert int(version["v"]) == 6
    table = await db.fetchone(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='top_ups'"
    )
    assert table is not None
    cols = await db.fetchall("PRAGMA table_info(top_ups)")
    names = {row["name"] for row in cols}
    assert {"account_id", "amount_minor", "currency", "applied_to_balance", "reversed_at"} <= names
    wd_cols = await db.fetchall("PRAGMA table_info(expected_withdrawals)")
    wd_names = {row["name"] for row in wd_cols}
    assert "actual_amount_minor" in wd_names
    assert "origin" in wd_names
    hist_cols = await db.fetchall("PRAGMA table_info(balance_history)")
    hist_names = {row["name"] for row in hist_cols}
    assert "source" in hist_names
    await db.close()
