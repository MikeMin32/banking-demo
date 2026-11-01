from __future__ import annotations

import pytest

from app.services.container import Services
from app.services.withdrawals import WithdrawalError
from tests.conftest import draft


async def test_create_charge_does_not_change_recorded_balance(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="1000.00")
    )
    charge = await services.withdrawals.create(account.id, "250.00")
    reloaded = await services.accounts.get(account.id)
    projection = await services.withdrawals.projection(account.id)
    assert reloaded.balance_minor == 100000
    assert charge.status == "pending"
    assert charge.amount_minor == 25000
    assert projection.pending_minor == 25000
    assert projection.available_minor == 75000


async def test_pending_reduces_available_and_complete_deducts_once(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="1000")
    )
    first = await services.withdrawals.create(account.id, "200")
    second = await services.withdrawals.create(account.id, "50")
    projection = await services.withdrawals.projection(account.id)
    assert projection.pending_minor == 25000
    assert projection.available_minor == 75000
    assert projection.recorded_minor == 100000

    await services.withdrawals.complete(first.id)
    after_complete = await services.withdrawals.projection(account.id)
    recorded = await services.accounts.get(account.id)
    assert recorded.balance_minor == 80000
    assert after_complete.pending_minor == 5000
    assert after_complete.available_minor == 75000
    assert (await services.withdrawals.get(first.id)).applied_to_balance

    again = await services.withdrawals.complete(first.id)
    assert again.status == "completed"
    assert (await services.accounts.get(account.id)).balance_minor == 80000

    await services.withdrawals.cancel(second.id)
    after_cancel = await services.withdrawals.projection(account.id)
    assert after_cancel.pending_minor == 0
    assert after_cancel.available_minor == 80000
    assert (await services.accounts.get(account.id)).balance_minor == 80000


async def test_complete_idempotent_and_writes_history(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="EUR", balance_raw="80.00")
    )
    charge = await services.withdrawals.create(account.id, "80.00")
    completed = await services.withdrawals.complete(charge.id)
    assert completed.status == "completed"
    assert completed.applied_to_balance
    assert (await services.accounts.get(account.id)).balance_minor == 0
    repeated = await services.withdrawals.complete(charge.id)
    assert repeated.status == "completed"
    assert (await services.accounts.get(account.id)).balance_minor == 0
    _, entries, total = await services.balances.history_page(account.id, page=0, page_size=10)
    assert total == 1
    assert entries[0].old_balance_minor == 8000
    assert entries[0].new_balance_minor == 0


async def test_cancel_releases_reservation(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    charge = await services.withdrawals.create(account.id, "200")
    await services.withdrawals.cancel(charge.id)
    projection = await services.withdrawals.projection(account.id)
    assert projection.pending_minor == 0
    assert projection.available_minor == 100000
    assert (await services.accounts.get(account.id)).balance_minor == 100000


async def test_edit_pending_amount_recalculates_available(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    charge = await services.withdrawals.create(account.id, "200")
    updated = await services.withdrawals.update(charge.id, raw_amount="350")
    projection = await services.withdrawals.projection(account.id)
    assert updated.amount_minor == 35000
    assert projection.available_minor == 65000
    assert (await services.accounts.get(account.id)).balance_minor == 100000


async def test_delete_completed_does_not_reverse(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    charge = await services.withdrawals.create(account.id, "200")
    await services.withdrawals.complete(charge.id)
    await services.withdrawals.delete(charge.id)
    assert (await services.accounts.get(account.id)).balance_minor == 80000


async def test_legacy_completed_is_not_retroactively_deducted(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.db.execute(
        """
        INSERT INTO expected_withdrawals (
            account_id, amount_minor, status, created_at, updated_at, completed_at, applied_to_balance
        ) VALUES (?, 20000, 'completed', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00',
                  '2026-01-01T00:00:00+00:00', 0)
        """,
        (account.id,),
    )
    row = await services.db.fetchone("SELECT id FROM expected_withdrawals ORDER BY id DESC LIMIT 1")
    leftover = await services.withdrawals.complete(int(row["id"]))
    assert leftover.status == "completed"
    assert leftover.applied_to_balance is False
    assert (await services.accounts.get(account.id)).balance_minor == 100000
    projection = await services.withdrawals.projection(account.id)
    assert projection.available_minor == 100000


async def test_manual_balance_update_keeps_pending(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="1000"))
    await services.withdrawals.create(account.id, "200")
    result = await services.balances.update_balance(account.id, "1500")
    projection = await services.withdrawals.projection(account.id)
    assert result.new_balance_minor == 150000
    assert projection.pending_minor == 20000
    assert projection.available_minor == 130000


async def test_rejects_zero_and_negative_charge(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="10"))
    with pytest.raises(WithdrawalError):
        await services.withdrawals.create(account.id, "0")
    with pytest.raises(WithdrawalError):
        await services.withdrawals.create(account.id, "-5")


async def test_edit_amount_and_delete_pending(services: Services) -> None:
    account = await services.accounts.create(draft(balance_raw="10"))
    charge = await services.withdrawals.create(account.id, "3")
    updated = await services.withdrawals.update(charge.id, raw_amount="4.50")
    assert updated.amount_minor == 450
    await services.withdrawals.delete(updated.id)
    with pytest.raises(WithdrawalError):
        await services.withdrawals.get(updated.id)
