from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.container import Services
from tests.conftest import draft
from app.services.dashboard import is_stale
from app.services.money import format_amount


async def test_balance_update_and_history(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="100.00")
    )
    result = await services.balances.update_balance(account.id, "85.50")
    assert result.old_balance_minor == 10000
    assert result.new_balance_minor == 8550
    assert result.account.balance_minor == 8550
    _, entries, total = await services.balances.history_page(account.id, page=0, page_size=10)
    assert total == 1
    assert entries[0].old_balance_minor == 10000
    assert entries[0].new_balance_minor == 8550
    assert format_amount(entries[0].new_balance_minor, "USD") == "85.50 USD"


async def test_negative_and_zero_balances(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Card", bank_name="Bank", currency="EUR", balance_raw="0")
    )
    zero = await services.balances.update_balance(account.id, "0")
    assert zero.new_balance_minor == 0
    negative = await services.balances.update_balance(account.id, "-12.30")
    assert negative.new_balance_minor == -1230


async def test_confirm_checked_does_not_change_balance(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="50")
    )
    before = account.balance_minor
    old_checked = account.last_checked_at
    updated = await services.balances.confirm_checked(account.id)
    assert updated.balance_minor == before
    assert updated.last_checked_at != old_checked
    _, entries, total = await services.balances.history_page(account.id, page=0, page_size=10)
    assert total == 0


async def test_mark_all_checked_does_not_change_balances(services: Services) -> None:
    a = await services.accounts.create(
        draft(display_name="A", bank_name="Bank", currency="USD", balance_raw="11")
    )
    b = await services.accounts.create(
        draft(display_name="B", bank_name="Bank", currency="EUR", balance_raw="22")
    )
    count = await services.balances.confirm_all_checked()
    assert count == 2
    assert (await services.accounts.get(a.id)).balance_minor == 1100
    assert (await services.accounts.get(b.id)).balance_minor == 2200


async def test_stale_detection(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="1")
    )
    now = datetime.now(timezone.utc)
    assert not is_stale(account, now=now, stale_hours=24)
    account.last_checked_at = (now - timedelta(hours=25)).isoformat()
    assert is_stale(account, now=now, stale_hours=24)
    account.last_checked_at = None
    assert is_stale(account, now=now, stale_hours=24)
