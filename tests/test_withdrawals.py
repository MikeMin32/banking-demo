from __future__ import annotations

import pytest

from tests.conftest import draft
from app.services.container import Services
from app.services.withdrawals import WithdrawalError


async def test_create_withdrawal_does_not_change_balance(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="1000.00")
    )
    withdrawal = await services.withdrawals.create(account.id, "250.00", description="Payroll")
    reloaded = await services.accounts.get(account.id)
    assert reloaded.balance_minor == 100000
    assert withdrawal.status == "pending"
    assert withdrawal.amount_minor == 25000


async def test_projected_remaining_uses_pending_only(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="1000")
    )
    first = await services.withdrawals.create(account.id, "200")
    second = await services.withdrawals.create(account.id, "50")
    projection = await services.withdrawals.projection(account.id)
    assert projection.pending_minor == 25000
    assert projection.projected_minor == 75000

    await services.withdrawals.complete(first.id)
    after_complete = await services.withdrawals.projection(account.id)
    assert after_complete.pending_minor == 5000
    assert after_complete.projected_minor == 95000
    assert (await services.accounts.get(account.id)).balance_minor == 100000

    await services.withdrawals.cancel(second.id)
    after_cancel = await services.withdrawals.projection(account.id)
    assert after_cancel.pending_minor == 0
    assert after_cancel.projected_minor == 100000
    assert (await services.accounts.get(account.id)).balance_minor == 100000


async def test_complete_does_not_silently_change_balance(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="EUR", balance_raw="80.00")
    )
    withdrawal = await services.withdrawals.create(account.id, "80.00")
    completed = await services.withdrawals.complete(withdrawal.id)
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert (await services.accounts.get(account.id)).balance_minor == 8000
    with pytest.raises(WithdrawalError):
        await services.withdrawals.complete(withdrawal.id)


async def test_rejects_zero_and_negative_withdrawal(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="10")
    )
    with pytest.raises(WithdrawalError):
        await services.withdrawals.create(account.id, "0")
    with pytest.raises(WithdrawalError):
        await services.withdrawals.create(account.id, "-5")


async def test_edit_amount_and_delete(services: Services) -> None:
    account = await services.accounts.create(
        draft(display_name="Ops", bank_name="Chase", currency="USD", balance_raw="10")
    )
    withdrawal = await services.withdrawals.create(account.id, "3", description="old")
    updated = await services.withdrawals.update(withdrawal.id, raw_amount="4.50", description="new")
    assert updated.amount_minor == 450
    assert updated.description == "new"
    await services.withdrawals.delete(updated.id)
    with pytest.raises(WithdrawalError):
        await services.withdrawals.get(updated.id)
