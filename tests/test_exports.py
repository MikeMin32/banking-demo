from __future__ import annotations

from pathlib import Path

from app.services.backup import backup_database
from tests.conftest import draft
from app.services.container import Services
from app.database.connection import Database


async def test_exports_exclude_secrets(services: Services) -> None:
    account = await services.accounts.create(
        draft(
            company_name="Secretive",
            bank_name="Bank",
            currency="USD",
            balance_raw="10",
            login_url="https://bank.example/login",
            login_username="ada@example.com",
            password_manager_ref="1password://bank",
            notes="pin 1234",
        )
    )
    await services.deposits.upsert(
        account.id,
        {"iban": "DE89370400440532013000", "account_number": "000123", "swift_bic": "COBADEFFXXX"},
        "2026-01-01T00:00:00+00:00",
    )
    await services.withdrawals.create(account.id, "1.00", description="test")
    await services.balances.update_balance(account.id, "9.00")

    accounts_csv = (await services.exports.accounts_csv()).decode()
    history_csv = (await services.exports.balance_history_csv()).decode()
    withdrawals_csv = (await services.exports.withdrawals_csv()).decode()
    combined = accounts_csv + history_csv + withdrawals_csv
    for secret in (
        "https://bank.example/login",
        "ada@example.com",
        "1password://bank",
        "DE89370400440532013000",
        "000123",
        "COBADEFFXXX",
        "pin 1234",
    ):
        assert secret not in combined
    assert "Secretive" in accounts_csv
    assert "USD" in accounts_csv


async def test_backup_creates_file(db: Database, tmp_path: Path) -> None:
    dest = tmp_path / "backups"
    path = await backup_database(db, dest)
    assert path.exists()
    assert path.stat().st_size > 0
