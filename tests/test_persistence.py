from __future__ import annotations

from app.config import Settings
from app.database.connection import Database
from app.services.container import build_services
from tests.conftest import draft


async def test_data_survives_reconnect(tmp_path, settings: Settings) -> None:
    path = str(tmp_path / "persist.db")
    db1 = Database(path)
    await db1.connect()
    await db1.init()
    services = build_services(db1, settings)
    account = await services.accounts.create(
        draft(company_name="Keep", bank_name="Bank", currency="USD", balance_raw="42.00")
    )
    await services.balances.update_balance(account.id, "40.00")
    await services.withdrawals.create(account.id, "5.00", description="rent")
    await services.deposits.upsert(account.id, {"iban": "DE001234", "account_number": "00123"}, "2026-01-01T00:00:00+00:00")
    account_id = account.id
    await db1.close()

    db2 = Database(path)
    await db2.connect()
    await db2.init()
    services2 = build_services(db2, settings)
    reloaded = await services2.accounts.get(account_id)
    assert reloaded.display_name == "VM 1 - Keep"
    assert reloaded.balance_minor == 4000
    _, history, total = await services2.balances.history_page(account_id, page=0, page_size=10)
    assert total == 1
    projection = await services2.withdrawals.projection(account_id)
    assert projection.pending_minor == 500
    details = await services2.deposits.get(account_id)
    assert details is not None
    assert details.iban == "DE001234"
    assert details.account_number == "00123"  # leading zeros preserved
    await db2.close()


async def test_wal_and_foreign_keys(db: Database) -> None:
    journal = await db.fetchone("PRAGMA journal_mode")
    fkeys = await db.fetchone("PRAGMA foreign_keys")
    assert str(journal[0]).lower() == "wal"
    assert int(fkeys[0]) == 1
