from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.database.connection import Database
from app.services.accounts import AccountDraft
from app.services.container import build_services
from app.services.demo_accounts import (
    DemoSeedBlocked,
    apply_demo_accounts,
    _production_block_reason,
)
from app.services.money import parse_to_minor


def _settings(tmp_path, **overrides) -> Settings:
    values = dict(
        bot_token="123456:TESTTOKEN",
        owner_telegram_id=1001,
        database_path=str(tmp_path / "live.db"),
        timezone="Europe/Kyiv",
        reminder_time="09:00",
        log_level="WARNING",
        dev_allow_any_user=False,
    )
    values.update(overrides)
    return Settings(**values)


EXPECTED_BALANCES = {9: "12450.75", 4: "8725.40", 32: "5340.20"}
EXPECTED_PENDING = {9: "3700.00", 4: "1500.00", 32: "1450.00"}


async def test_seed_replaces_obsolete_demo_and_is_idempotent(tmp_path) -> None:
    settings = _settings(tmp_path)
    db = Database(settings.database_path)
    await db.connect()
    await db.init()
    services = build_services(db, settings)
    await services.accounts.create(
        AccountDraft(vm_number=1, company_name="Operating", bank_name="Chase", currency="USD", balance_raw="10")
    )
    await services.account_repo.update_fields(
        1, {"display_name": "Operating", "company_name": "Operating"}, "2026-01-01T00:00:00+00:00"
    )
    keep = await services.accounts.create(
        AccountDraft(vm_number=88, company_name="Real Client", bank_name="N26", currency="EUR", balance_raw="50")
    )
    await db.close()

    first = await apply_demo_accounts(settings)
    assert any("Operating" in item for item in first.removed)
    assert len(first.created) == 3
    assert any("Real Client" in item for item in first.preserved)
    assert first.history_written == 24
    assert first.withdrawals_upserted == 9
    assert first.activity_skipped == []

    second = await apply_demo_accounts(settings)
    assert second.removed == []
    assert second.created == []
    assert second.history_written == 0
    assert second.withdrawals_upserted == 0

    db2 = Database(settings.database_path)
    await db2.connect()
    services2 = build_services(db2, settings)
    active = await services2.accounts.list_active()
    names = {account.display_name for account in active}
    assert names == {
        "VM 4 - Automation Direct",
        "VM 9 - LeBon Shoppe",
        "VM 32 - Graphics Press",
        "VM 88 - Real Client",
    }
    targets = [account for account in active if account.vm_number in {4, 9, 32}]
    assert all(account.banking_provider == "Airwallex" for account in targets)
    assert all(account.currency == "USD" for account in targets)
    for account in targets:
        assert account.balance_minor == parse_to_minor(EXPECTED_BALANCES[account.vm_number], "USD")
        history = await services2.balances.history.list_for_account(account.id, limit=20)
        assert len(history) == 8
        assert history[0].new_balance_minor == account.balance_minor
        withdrawals = await services2.withdrawals.withdrawals.list_withdrawals(account_id=account.id, limit=20)
        assert len(withdrawals) == 3
        pending = await services2.withdrawals.withdrawals.pending_total_for_account(account.id)
        assert pending == parse_to_minor(EXPECTED_PENDING[account.vm_number], "USD")
        for item in withdrawals:
            if item.status == "pending":
                assert item.completed_at is None
            elif item.status == "completed":
                assert item.completed_at is not None
    real = await services2.accounts.get(keep.id)
    assert real.balance_minor == 5000
    real_withdrawals = await services2.withdrawals.withdrawals.list_withdrawals(account_id=keep.id, limit=20)
    assert real_withdrawals == []
    await db2.close()


async def test_seed_dashboard_totals_from_database(tmp_path) -> None:
    settings = _settings(tmp_path)
    await apply_demo_accounts(settings)
    db = Database(settings.database_path)
    await db.connect()
    services = build_services(db, settings)
    snap = await services.dashboard.snapshot(stale_hours=24)
    assert snap.active_count == 3
    usd = snap.by_currency["USD"]
    assert usd.balance_minor == parse_to_minor("26516.35", "USD")
    assert usd.pending_minor == parse_to_minor("6650.00", "USD")
    assert usd.projected_minor == parse_to_minor("19866.35", "USD")
    assert snap.pending_withdrawal_count == 5
    cancelled = await services.withdrawals.withdrawals.list_withdrawals(status="cancelled", limit=20)
    assert len(cancelled) == 1
    assert cancelled[0].amount_minor == parse_to_minor("950.00", "USD")
    completed = await services.withdrawals.withdrawals.list_withdrawals(status="completed", limit=20)
    assert len(completed) == 3
    await db.close()


async def test_seed_skips_unexpected_activity(tmp_path) -> None:
    settings = _settings(tmp_path)
    first = await apply_demo_accounts(settings)
    assert first.activity_skipped == []
    db = Database(settings.database_path)
    await db.connect()
    services = build_services(db, settings)
    account = await services.accounts.find_by_vm_company(9, "LeBon Shoppe")
    assert account is not None
    await services.withdrawals.create(account.id, "99.00", description="User-entered payout")
    await db.close()

    second = await apply_demo_accounts(settings)
    assert "VM 9 - LeBon Shoppe" in second.activity_skipped
    db2 = Database(settings.database_path)
    await db2.connect()
    services2 = build_services(db2, settings)
    withdrawals = await services2.withdrawals.withdrawals.list_withdrawals(account_id=account.id, limit=20)
    assert any(item.description == "User-entered payout" for item in withdrawals)
    assert len(withdrawals) == 4
    await db2.close()


async def test_production_path_is_blocked(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path, database_path=str(tmp_path / "production.db"))
    assert _production_block_reason(settings) is not None
    with pytest.raises(DemoSeedBlocked):
        await apply_demo_accounts(settings)
    monkeypatch.setenv("ENVIRONMENT", "production")
    demo_settings = _settings(tmp_path / "other")
    with pytest.raises(DemoSeedBlocked):
        await apply_demo_accounts(demo_settings)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    os.environ.pop("BANK_MANAGER_ENV", None)
